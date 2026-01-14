from fastapi import FastAPI, APIRouter, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
from bson import ObjectId
import json
from datetime import datetime

# --- DATABASE SETUP ---
# Replace with your actual connection string
from pymongo import MongoClient
client = MongoClient("YOUR_MONGODB_URI_HERE")
db = client["billing_db"]
store_collection = db["products"]
history_collection = db["invoices"]
settings_collection = db["settings"]

app = FastAPI(title="Yuku Protocol API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODELS ---
class ProductSchema(BaseModel):
    name: str
    price: float
    cost: float = 0.0
    stock: int = 0
    imgs: List[str] = []

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

# --- ROUTES ---

@app.get("/store/items")
async def get_items():
    return await run_in_threadpool(lambda: list(store_collection.find({}, {"_id": 0})))

@app.post("/store/items")
async def add_item(item: ProductSchema):
    def db_op():
        store_collection.update_one({"name": item.name}, {"$set": item.model_dump()}, upsert=True)
        return {"status": "success"}
    return await run_in_threadpool(db_op)

@app.get("/store/history")
async def get_history():
    return await run_in_threadpool(lambda: list(history_collection.find({}, {"_id": 0}).sort("inv_id", -1).limit(100)))

@app.post("/store/history")
async def save_invoice(inv: InvoiceSchema):
    def db_op():
        # 1. Save Invoice
        history_collection.insert_one(inv.model_dump())
        # 2. Update Stock
        for i in inv.items:
            if not i.get('isManual'):
                store_collection.update_one({"name": i['name']}, {"$inc": {"stock": -i['qty']}})
        return {"status": "saved"}
    return await run_in_threadpool(db_op)

@app.patch("/store/history/{inv_id}")
async def update_payment(inv_id: int, data: Dict[str, Any]):
    amount = float(data.get("amount", 0))
    def db_op():
        inv = history_collection.find_one({"inv_id": inv_id})
        if not inv: return None
        new_paid = float(inv.get("paid", 0)) + amount
        new_due = max(0, float(inv.get("total", 0)) - new_paid)
        new_status = "Paid" if new_due <= 0.1 else "Partial"
        history_collection.update_one(
            {"inv_id": inv_id},
            {
                "$set": {"paid": new_paid, "due": new_due, "status": new_status},
                "$push": {"history": {"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "amount": amount, "type": "Partial Payment"}}
            }
        )
        return {"status": "updated"}
    return await run_in_threadpool(db_op)

@app.get("/store/settings")
async def get_settings():
    return await run_in_threadpool(lambda: settings_collection.find_one({}, {"_id": 0}) or {"name": "My Shop", "addr": "India", "note": "Thank you"})

@app.post("/store/settings")
async def update_settings(data: Dict[str, Any]):
    await run_in_threadpool(lambda: settings_collection.update_one({}, {"$set": data}, upsert=True))
    return {"status": "updated"}

# --- PUSH NOTIFICATION STUB ---
@app.post("/webpush/send-test")
async def send_test_push(authorization: str = Header(None)):
    # This matches your Dashboard logic. 
    # In production, this would trigger your FCM/VAPID logic.
    return {"message": "System Alert Triggered Successfully"}

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
