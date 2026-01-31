from fastapi import APIRouter, HTTPException, Depends, status, Body
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
import os
# from pymongo import MongoClient - Removed
from database import db # Direct db import from updated database.py

router = APIRouter(prefix="/store", tags=["Store"])

# --- HELPERS ---
def get_collection(name: str):
    if db is None:
        raise HTTPException(500, "Database Disconnected")
    # Mapping old collection names to new ones if needed, 
    # or just returning the collection object from db
    if name == "products": return db.store_items
    if name == "invoices": return db.store_history
    if name == "settings": return db.store_settings
    return db[name]

async def check_idempotency(col, query):
    if await col.find_one(query):
        raise HTTPException(status_code=409, detail="Duplicate Entry")

# --- MODELS ---
class ProductSchema(BaseModel):
    name: str
    price: float
    cost: float = 0.0
    stock: int = 0
    imgs: List[str] = []

class InvoiceItem(BaseModel):
    id: str
    name: str
    price: float
    cost: float = 0.0
    qty: int
    isManual: bool = False
    imgs: List[str] = []

class PaymentRecord(BaseModel):
    date: str
    amount: float
    type: str

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
    items: List[InvoiceItem]
    history: List[PaymentRecord] = []

class SettingsSchema(BaseModel):
    name: str = "My Shop"
    addr: str = "India"
    note: str = "Thank you."
    taxRate: float = 0.0
    sign: Optional[str] = None
    showMan: bool = True
    showTax: bool = True
    showDisc: bool = True
    tourDone: bool = False

class PatchPayment(BaseModel):
    amount: float

# --- ROUTES ---

# 1. GET ITEMS (Async)
@router.get("/items", response_model=List[ProductSchema])
async def get_items():
    col = get_collection("products")
    # Motor returns a cursor, use to_list
    items = await col.find({}, {"_id": 0}).to_list(length=1000)
    return items

# 2. ADD NEW ITEM (Strictly Add - Async)
@router.post("/items")
async def add_item(item: ProductSchema):
    col = get_collection("products")
    # Added await
    if await col.find_one({"name": item.name}):
        raise HTTPException(status_code=409, detail=f"Product '{item.name}' already exists.")
    
    # Added await
    await col.insert_one(item.model_dump())
    return {"status": "success", "action": "created", "name": item.name}

# 3. UPDATE ITEM (Async)
@router.put("/items/{original_name}")
async def update_item(original_name: str, item: ProductSchema):
    col = get_collection("products")
    
    # Added await
    existing = await col.find_one({"name": original_name})
    if not existing:
        raise HTTPException(status_code=404, detail="Product not found")

    if item.name != original_name:
        # Added await
        if await col.find_one({"name": item.name}):
            raise HTTPException(status_code=409, detail=f"Product name '{item.name}' is already taken.")

    # Added await
    await col.update_one({"name": original_name}, {"$set": item.model_dump()})
    return {"status": "success", "action": "updated", "name": item.name}

# 4. DELETE ITEM (Async)
@router.delete("/items/{name}")
async def delete_item(name: str):
    col = get_collection("products")
    
    # Added await
    result = await col.delete_one({"name": name})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"status": "deleted", "name": name}

# 5. GET HISTORY (Async)
@router.get("/history", response_model=List[InvoiceSchema])
async def get_history(skip: int = 0, limit: int = 100):
    col = get_collection("invoices")
    # Motor cursor chaining
    cursor = col.find({}, {"_id": 0}).sort("inv_id", -1).skip(skip).limit(limit)
    invoices = await cursor.to_list(length=limit)
    return invoices

# 6. SAVE INVOICE (Async)
@router.post("/history", status_code=201)
async def save_invoice(inv: InvoiceSchema):
    inv_col = get_collection("invoices")
    prod_col = get_collection("products")
    
    # Await helper
    await check_idempotency(inv_col, {"inv_id": inv.inv_id})
    
    # Added await
    await inv_col.insert_one(inv.model_dump())

    for item in inv.items:
        if not item.isManual:
            # Added await
            await prod_col.update_one({"name": item.name}, {"$inc": {"stock": -item.qty}})
            
    return {"status": "saved", "inv_id": inv.inv_id}

# 7. VOID INVOICE (Async)
@router.patch("/history/{inv_id}/void")
async def void_invoice(inv_id: int):
    inv_col = get_collection("invoices")
    prod_col = get_collection("products")
    
    # Added await
    inv = await inv_col.find_one({"inv_id": inv_id})
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    if inv.get("status") == "Void":
         raise HTTPException(status_code=400, detail="Invoice is already Void")
        
    for item in inv.get("items", []):
        if not item.get("isManual", False):
            # Added await
            await prod_col.update_one({"name": item["name"]}, {"$inc": {"stock": item["qty"]}})
            
    log_entry = { "date": datetime.now().strftime("%d/%m/%Y, %I:%M %p"), "amount": 0, "type": "VOIDED" }
    
    # Added await
    await inv_col.update_one({"inv_id": inv_id}, { "$set": {"status": "Void", "due": 0.0}, "$push": {"history": log_entry} })
    return {"status": "voided", "inv_id": inv_id}

# 8. UPDATE PAYMENT (Async)
@router.patch("/history/{inv_id}")
async def update_payment(inv_id: int, payload: PatchPayment):
    amount = payload.amount
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    col = get_collection("invoices")
    
    # Added await
    inv = await col.find_one({"inv_id": inv_id})
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if inv.get("status") == "Void":
        raise HTTPException(status_code=400, detail="Cannot pay for Voided invoice")

    current_paid = float(inv.get("paid", 0))
    total = float(inv.get("total", 0))
    
    new_paid = current_paid + amount
    if new_paid > (total + 1.0):
        raise HTTPException(status_code=400, detail=f"Overpayment! Max allowed: {total - current_paid}")

    new_due = max(0.0, total - new_paid)
    new_status = "Paid" if new_due <= 0.5 else "Partial"

    log_entry = { "date": datetime.now().strftime("%d/%m/%Y, %I:%M %p"), "amount": amount, "type": "Settlement" }
    
    # Added await
    await col.update_one({"inv_id": inv_id}, { "$set": {"paid": new_paid, "due": new_due, "status": new_status}, "$push": {"history": log_entry} })

    return {"status": "updated"}

# 9. SETTINGS (Async)
@router.get("/settings", response_model=SettingsSchema)
async def get_settings():
    col = get_collection("settings")
    # Added await
    data = await col.find_one({}, {"_id": 0})
    return data if data else SettingsSchema().model_dump()

@router.post("/settings")
async def update_settings(sets: SettingsSchema):
    col = get_collection("settings")
    # Added await
    await col.update_one({}, {"$set": sets.model_dump()}, upsert=True)
    return {"status": "updated"}