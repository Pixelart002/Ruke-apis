from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, BeforeValidator
from typing_extensions import Annotated
from bson import ObjectId
import json
from datetime import datetime

# Import your database collections
from database import store_collection, history_collection, settings_collection

router = APIRouter(prefix="/store", tags=["Store"])

# --- 1. MODELS ---
PyObjectId = Annotated[str, BeforeValidator(str)]

class ProductSchema(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    name: str
    price: float
    cost: float = 0.0
    stock: int = 0
    imgs: List[str] = []

class InvoiceSchema(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    inv_id: int
    date: str
    client: str
    addr: str = ""
    phone: str = ""
    total: float
    status: str
    paid: float
    due: float
    items: List[Dict[str, Any]]
    history: List[Dict[str, Any]]

class SettingsSchema(BaseModel):
    name: str = "My Shop"
    addr: str = "New Delhi, India"
    note: str = "Thank you."
    sign: Optional[str] = None
    showMan: bool = True
    tourDone: bool = False

# --- 2. WEBSOCKET MANAGER ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try: await connection.send_text(json.dumps(message))
            except: pass

manager = ConnectionManager()

# --- 3. INVENTORY ROUTES ---

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
    def db_op():
        store_collection.delete_one({"_id": ObjectId(item_id)})
    await run_in_threadpool(db_op)
    await manager.broadcast({"type": "error", "msg": "Item Deleted", "action": "refresh_inv"})
    return {"status": "deleted"}

# --- 4. HISTORY ROUTES ---

@router.get("/history", response_model=List[InvoiceSchema])
async def get_history():
    # Return last 50 invoices sorted by ID
    return await run_in_threadpool(lambda: list(history_collection.find().sort("inv_id", -1).limit(50)))

@router.post("/history")
async def save_invoice(inv: InvoiceSchema):
    inv_dict = inv.model_dump(by_alias=True, exclude=["id"])
    
    def db_op():
        # 1. Save Invoice
        history_collection.insert_one(inv_dict)
        # 2. Update Stock
        for i in inv.items:
            if not i.get('isManual') and 'id' in i:
                try:
                    store_collection.update_one(
                        {"_id": ObjectId(i['id'])}, 
                        {"$inc": {"stock": -i['qty']}}
                    )
                except: pass
    
    await run_in_threadpool(db_op)
    await manager.broadcast({"type": "success", "msg": f"Invoice #{inv.inv_id} Created", "action": "refresh_hist"})
    return {"status": "saved"}

# --- 5. SETTINGS ROUTES ---

@router.get("/settings", response_model=SettingsSchema)
async def get_settings():
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
    def db_op():
        settings_collection.update_one({}, {"$set": sets.model_dump()}, upsert=True)
    await run_in_threadpool(db_op)
    await manager.broadcast({"type": "info", "msg": "Settings Updated", "action": "refresh_sets"})
    return {"status": "updated"}

# --- 6. WEBSOCKET ---
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True: await websocket.receive_text()
    except WebSocketDisconnect: manager.disconnect(websocket)
@router.patch("/history/{inv_id}")
async def update_invoice_payment(inv_id: str, payment_data: Dict[str, Any]):
    amount = payment_data.get("amount", 0)
    
    def db_op():
        # 1. Determine if search is by integer inv_id or MongoDB ObjectId
        try:
            # Try numeric ID first (e.g., 1001)
            search_query = {"inv_id": int(inv_id)}
        except ValueError:
            # Fallback to MongoDB string ID
            search_query = {"_id": ObjectId(inv_id)}

        # 2. Find the existing invoice
        invoice = history_collection.find_one(search_query)
        if not invoice:
            return None
        
        # 3. Calculate new totals
        current_paid = float(invoice.get("paid", 0))
        total = float(invoice.get("total", 0))
        
        new_paid = round(current_paid + float(amount), 2)
        new_due = max(0, round(total - new_paid, 2))
        
        # 4. Determine new status
        new_status = "Paid" if new_due < 0.5 else "Partial"
        
        # 5. Prepare payment entry
        payment_entry = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "amount": float(amount),
            "type": "Partial Payment" if new_due > 0 else "Full Payment"
        }
        
        # 6. Update document
        history_collection.update_one(
            search_query,
            {
                "$set": {
                    "paid": new_paid,
                    "due": new_due,
                    "status": new_status
                },
                "$push": {"history": payment_entry}
            }
        )
        return {"inv_id": invoice.get("inv_id"), "status": new_status, "amount": amount}

    result = await run_in_threadpool(db_op)
    
    if not result:
        raise HTTPException(status_code=404, detail=f"Invoice {inv_id} not found")
        
    # Broadcast to update all connected clients
    await manager.broadcast({
        "type": "success", 
        "msg": f"Payment of ₹{result['amount']} recorded for #{result['inv_id']}", 
        "action": "refresh_hist"
    })
    
    return result
    
    
    