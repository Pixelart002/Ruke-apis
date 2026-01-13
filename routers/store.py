from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from typing import List, Optional, Any
from pydantic import BaseModel, Field, BeforeValidator
from typing_extensions import Annotated
from bson import ObjectId
import json

# Import Collections
from database import store_collection, history_collection, settings_collection

router = APIRouter(prefix="/store", tags=["Store"])

# --- 1. MODELS ---
PyObjectId = Annotated[str, BeforeValidator(str)]

class ProductSchema(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    name: str
    price: float
    stock: int = 0
    imgs: List[str] = []

class InvoiceSchema(BaseModel):
    id: int # Invoice Number (e.g., 1001)
    date: str
    client: str
    addr: str = ""
    phone: str = ""
    total: float
    status: str # Paid, Pending, Partial
    paid: float
    due: float
    items: List[Any] # Full cart details
    history: List[Any] # Payment history logs

class SettingsSchema(BaseModel):
    name: str = "My Shop"
    addr: str = "New Delhi, India"
    note: str = "Thank you for shopping."
    sign: Optional[str] = None # Base64 Image
    showMan: bool = True
    tourDone: bool = False

# --- 2. WEBSOCKETS ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active_connections.append(ws)
    def disconnect(self, ws: WebSocket):
        if ws in self.active_connections: self.active_connections.remove(ws)
    async def broadcast(self, msg: dict):
        for c in self.active_connections:
            try: await c.send_text(json.dumps(msg))
            except: pass

manager = ConnectionManager()

# --- 3. INVENTORY ENDPOINTS (Existing) ---
@router.get("/items", response_model=List[ProductSchema])
async def get_items():
    return await run_in_threadpool(lambda: list(store_collection.find()))

@router.post("/items")
async def add_item(item: ProductSchema):
    item_dict = item.model_dump(by_alias=True, exclude=["id"])
    def db_op():
        res = store_collection.insert_one(item_dict)
        return store_collection.find_one({"_id": res.inserted_id})
    new_item = await run_in_threadpool(db_op)
    await manager.broadcast({"type": "success", "msg": f"Added: {item.name}", "action": "refresh_inv"})
    return new_item

@router.delete("/items/{item_id}")
async def delete_item(item_id: str):
    def db_op(): return store_collection.delete_one({"_id": ObjectId(item_id)})
    await run_in_threadpool(db_op)
    await manager.broadcast({"type": "error", "msg": "Item Deleted", "action": "refresh_inv"})
    return {"status": "deleted"}

# --- 4. HISTORY ENDPOINTS (New) ---
@router.get("/history", response_model=List[InvoiceSchema])
async def get_history():
    """Fetch last 100 invoices"""
    return await run_in_threadpool(lambda: list(history_collection.find().sort("id", -1).limit(100)))

@router.post("/history")
async def add_invoice(inv: InvoiceSchema):
    """Save Invoice"""
    inv_dict = inv.model_dump()
    await run_in_threadpool(lambda: history_collection.insert_one(inv_dict))
    await manager.broadcast({"type": "success", "msg": f"Invoice #{inv.id} Generated", "action": "refresh_hist"})
    return {"status": "saved"}

# --- 5. SETTINGS ENDPOINTS (New) ---
@router.get("/settings", response_model=SettingsSchema)
async def get_settings():
    """Get settings (or default if missing)"""
    def db_op():
        data = settings_collection.find_one({})
        if not data:
            default = SettingsSchema().model_dump()
            settings_collection.insert_one(default)
            return default
        return data
    return await run_in_threadpool(db_op)

@router.post("/settings")
async def update_settings(sets: SettingsSchema):
    """Update settings"""
    def db_op():
        # Upsert: Update if exists, Insert if not
        settings_collection.update_one({}, {"$set": sets.model_dump()}, upsert=True)
    await run_in_threadpool(db_op)
    await manager.broadcast({"type": "info", "msg": "Shop Settings Updated", "action": "refresh_sets"})
    return {"status": "updated"}

# --- 6. WEBSOCKET ROUTE ---
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True: await websocket.receive_text()
    except WebSocketDisconnect: manager.disconnect(websocket)
