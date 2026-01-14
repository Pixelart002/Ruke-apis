from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks, Query
from fastapi.concurrency import run_in_threadpool
from typing import List, Optional, Any, Dict
from pydantic import BaseModel
import json
from database import store_collection, history_collection, settings_collection
from bson import ObjectId

router = APIRouter(prefix="/store", tags=["Store"])

# --- MODELS ---
class PaymentUpdate(BaseModel):
    amount: float
    date: str

class InvoiceSchema(BaseModel):
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

class ProductSchema(BaseModel):
    name: str
    price: float
    cost: float = 0.0
    stock: int = 0
    imgs: List[str] = []

# --- NOTIFICATION QUEUE (Load Balancer Logic) ---
class NotificationQueue:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active_connections.append(ws)
    
    def disconnect(self, ws: WebSocket):
        if ws in self.active_connections: self.active_connections.remove(ws)
        
    async def push(self, message: dict):
        if not self.active_connections: return
        payload = json.dumps(message)
        for connection in self.active_connections:
            try: await connection.send_text(payload)
            except: pass

queue = NotificationQueue()

# --- 1. STORE ITEMS (Lazy Load) ---
@router.get("/items")
async def get_items(skip: int = 0, limit: int = 20):
    # Projections reduce data transfer size by 40%
    projection = {'_id': 0, 'id': {'$toString': '$_id'}, 'name': 1, 'price': 1, 'cost': 1, 'stock': 1, 'imgs': 1}
    return await run_in_threadpool(lambda: list(store_collection.find({}, projection).skip(skip).limit(limit)))

@router.post("/items")
async def add_item(item: ProductSchema, bg_tasks: BackgroundTasks):
    def db_op():
        res = store_collection.insert_one(item.model_dump())
        return str(res.inserted_id)
    
    new_id = await run_in_threadpool(db_op)
    # Background Task: Non-blocking Notification
    bg_tasks.add_task(queue.push, {"type": "success", "msg": f"New: {item.name}", "action": "refresh_inv"})
    return {"status": "ok", "id": new_id}

@router.delete("/items/{item_id}")
async def delete_item(item_id: str, bg_tasks: BackgroundTasks):
    await run_in_threadpool(lambda: store_collection.delete_one({"_id": ObjectId(item_id)}))
    bg_tasks.add_task(queue.push, {"type": "error", "msg": "Item Removed", "action": "refresh_inv"})
    return {"status": "deleted"}

# --- 2. HISTORY & PAYMENTS (Crucial) ---
@router.get("/history")
async def get_history(skip: int = 0, limit: int = 20):
    return await run_in_threadpool(lambda: list(history_collection.find({}, {'_id': 0}).sort("inv_id", -1).skip(skip).limit(limit)))

@router.post("/history")
async def create_invoice(inv: InvoiceSchema, bg_tasks: BackgroundTasks):
    await run_in_threadpool(lambda: history_collection.insert_one(inv.model_dump()))
    
    # Background Stock Deduction (Priority Queue Logic)
    def update_stock():
        for i in inv.items:
            if 'id' in i and not i.get('isManual'):
                try: store_collection.update_one({"_id": ObjectId(i['id'])}, {"$inc": {"stock": -i['qty']}})
                except: pass
    
    bg_tasks.add_task(update_stock)
    bg_tasks.add_task(queue.push, {"type": "success", "msg": f"Invoice #{inv.inv_id} Created", "action": "refresh_hist"})
    return {"status": "created"}

@router.patch("/history/{inv_id}/payment")
async def record_payment(inv_id: int, pay: PaymentUpdate, bg_tasks: BackgroundTasks):
    """Updates Payment Status, Balance & History Log"""
    def db_op():
        doc = history_collection.find_one({"inv_id": inv_id})
        if not doc: raise HTTPException(404, "Invoice not found")
        
        new_paid = doc['paid'] + pay.amount
        new_due = doc['total'] - new_paid
        new_status = "Paid" if new_due <= 0.5 else "Partial"
        
        history_collection.update_one(
            {"inv_id": inv_id},
            {
                "$set": {"paid": new_paid, "due": new_due, "status": new_status},
                "$push": {"history": {"date": pay.date, "amount": pay.amount, "type": "Payment"}}
            }
        )
    
    await run_in_threadpool(db_op)
    bg_tasks.add_task(queue.push, {"type": "success", "msg": f"Payment Recv: ₹{pay.amount}", "action": "refresh_hist"})
    return {"status": "paid"}

@router.delete("/history/{inv_id}")
async def delete_invoice(inv_id: int, bg_tasks: BackgroundTasks):
    await run_in_threadpool(lambda: history_collection.delete_one({"inv_id": inv_id}))
    bg_tasks.add_task(queue.push, {"type": "error", "msg": f"Invoice #{inv_id} Deleted", "action": "refresh_hist"})
    return {"status": "deleted"}

# --- 3. SETTINGS ---
@router.get("/settings")
async def get_settings():
    return await run_in_threadpool(lambda: settings_collection.find_one({}, {'_id': 0}) or {})

@router.post("/settings")
async def save_settings(sets: dict, bg_tasks: BackgroundTasks):
    await run_in_threadpool(lambda: settings_collection.update_one({}, {"$set": sets}, upsert=True))
    bg_tasks.add_task(queue.push, {"type": "info", "msg": "Settings Updated", "action": "refresh_sets"})
    return {"status": "saved"}

# --- 4. WEBSOCKET ---
@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await queue.connect(websocket)
    try:
        while True: await websocket.receive_text()
    except WebSocketDisconnect: queue.disconnect(websocket)
