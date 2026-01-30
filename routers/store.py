from fastapi import APIRouter, HTTPException, Depends, status, Body
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
import os
from pymongo import MongoClient
from database import client as db_client 

router = APIRouter(prefix="/store", tags=["Store"])

# --- HELPERS ---
def get_collection(name: str):
    return db_client["billing_db"][name]

def check_idempotency(col, query):
    if col.find_one(query):
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

# 1. GET ITEMS
@router.get("/items", response_model=List[ProductSchema])
def get_items():
    return list(get_collection("products").find({}, {"_id": 0}))

# 2. ADD/UPDATE ITEM
@router.post("/items")
def add_item(item: ProductSchema):
    col = get_collection("products")
    # Upsert based on Name.
    result = col.update_one(
        {"name": item.name},
        {"$set": item.model_dump()},
        upsert=True
    )
    return {"status": "success", "action": "updated" if result.matched_count else "created"}

# 3. DELETE ITEM (Added)
@router.delete("/items/{name}")
def delete_item(name: str):
    col = get_collection("products")
    result = col.delete_one({"name": name})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"status": "deleted", "name": name}

# 4. GET HISTORY
@router.get("/history", response_model=List[InvoiceSchema])
def get_history(skip: int = 0, limit: int = 100):
    return list(get_collection("invoices").find({}, {"_id": 0}).sort("inv_id", -1).skip(skip).limit(limit))

# 5. SAVE INVOICE
@router.post("/history", status_code=201)
def save_invoice(inv: InvoiceSchema):
    inv_col = get_collection("invoices")
    prod_col = get_collection("products")
    
    check_idempotency(inv_col, {"inv_id": inv.inv_id})
    inv_col.insert_one(inv.model_dump())

    for item in inv.items:
        if not item.isManual:
            prod_col.update_one({"name": item.name}, {"$inc": {"stock": -item.qty}})
            
    return {"status": "saved", "inv_id": inv.inv_id}

# 6. DELETE INVOICE (Added - Restores Stock)
@router.delete("/history/{inv_id}")
def delete_invoice(inv_id: int):
    inv_col = get_collection("invoices")
    prod_col = get_collection("products")
    
    inv = inv_col.find_one({"inv_id": inv_id})
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    # Restore stock
    for item in inv.get("items", []):
        if not item.get("isManual", False):
            prod_col.update_one(
                {"name": item["name"]},
                {"$inc": {"stock": item["qty"]}}
            )
            
    inv_col.delete_one({"inv_id": inv_id})
    return {"status": "deleted", "inv_id": inv_id}

# 7. UPDATE PAYMENT
@router.patch("/history/{inv_id}")
def update_payment(inv_id: int, payload: PatchPayment):
    amount = payload.amount
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    col = get_collection("invoices")
    inv = col.find_one({"inv_id": inv_id})
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    current_paid = float(inv.get("paid", 0))
    total = float(inv.get("total", 0))
    
    new_paid = current_paid + amount
    
    # Strict Backend Check: Allow max 1 rupee buffer for round off
    if new_paid > (total + 1.0):
        raise HTTPException(status_code=400, detail=f"Overpayment! Max allowed: {total - current_paid}")

    new_due = max(0.0, total - new_paid)
    new_status = "Paid" if new_due <= 0.5 else "Partial"

    log_entry = {
        "date": datetime.now().strftime("%d/%m/%Y, %I:%M %p"),
        "amount": amount,
        "type": "Settlement"
    }

    col.update_one(
        {"inv_id": inv_id},
        {
            "$set": {"paid": new_paid, "due": new_due, "status": new_status},
            "$push": {"history": log_entry}
        }
    )

    return {"status": "updated"}

# 8. SETTINGS
@router.get("/settings", response_model=SettingsSchema)
def get_settings():
    data = get_collection("settings").find_one({}, {"_id": 0})
    return data if data else SettingsSchema().model_dump()

@router.post("/settings")
def update_settings(sets: SettingsSchema):
    get_collection("settings").update_one({}, {"$set": sets.model_dump()}, upsert=True)
    return {"status": "updated"}