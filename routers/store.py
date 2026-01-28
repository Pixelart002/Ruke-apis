from fastapi import APIRouter, HTTPException, Depends, status, Body
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
import os
from pymongo import MongoClient
# Assuming database.py exports 'db' or 'get_db'. 
# Adjust this import based on your exact database.py structure.
from database import db_client  # Ya jo bhi tumhara sync connection object hai

router = APIRouter(prefix="/store", tags=["Store"])

# --- DATABASE HELPER ---
# Is function se hum ensure karte hain ki humein sahi collection mile
def get_collection(name: str):
    db = db_client["billing_db"] # Apne DB ka naam yahan confirm karlena
    return db[name]

# --- PYDANTIC MODELS (Strict Validation) ---
class ProductSchema(BaseModel):
    name: str
    price: float
    cost: float = 0.0
    stock: int = 0
    imgs: List[str] = []

class InvoiceItem(BaseModel):
    id: str  # Frontend 'id' bhej raha hai
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

# --- ADVANCED UTILS ---
def check_idempotency(col, query):
    """
    Backend Debounce: Check karta hai ki record pehle se exist toh nahi karta.
    """
    if col.find_one(query):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate request detected. Resource already exists."
        )

# --- ROUTES (Note: Using 'def' for auto-threadpool) ---

# 1. GET ALL ITEMS
@router.get("/items", response_model=List[ProductSchema])
def get_items():
    col = get_collection("products")
    # Projection {_id: 0} use kiya taaki response fast ho
    items = list(col.find({}, {"_id": 0}))
    return items

# 2. ADD/UPDATE ITEM (Upsert)
@router.post("/items")
def add_item(item: ProductSchema):
    col = get_collection("products")
    # Upsert logic: Agar item hai to update, nahi to insert
    result = col.update_one(
        {"name": item.name},
        {"$set": item.model_dump()},
        upsert=True
    )
    action = "updated" if result.matched_count else "created"
    return {"status": "success", "action": action, "item": item.name}

# 3. GET HISTORY (With Pagination)
@router.get("/history", response_model=List[InvoiceSchema])
def get_history(skip: int = 0, limit: int = 100):
    col = get_collection("invoices")
    # Latest invoices pehle aayenge (sort by inv_id desc)
    invoices = list(col.find({}, {"_id": 0}).sort("inv_id", -1).skip(skip).limit(limit))
    return invoices

# 4. SAVE INVOICE (Transaction-like Logic)
@router.post("/history", status_code=status.HTTP_201_CREATED)
def save_invoice(inv: InvoiceSchema):
    inv_col = get_collection("invoices")
    prod_col = get_collection("products")

    # Step 1: Idempotency Check (Double save rokne ke liye)
    check_idempotency(inv_col, {"inv_id": inv.inv_id})

    # Step 2: Save Invoice
    inv_col.insert_one(inv.model_dump())

    # Step 3: Atomic Stock Update ($inc use kiya taaki race condition na ho)
    # Advanced practice: Bulk update use karna better hota hai heavy load pe,
    # par abhi loop kaafi hai simple store ke liye.
    for item in inv.items:
        if not item.isManual:
            prod_col.update_one(
                {"name": item.name},
                {"$inc": {"stock": -item.qty}}
            )
            
    return {"status": "saved", "inv_id": inv.inv_id}

# 5. SETTLE PAYMENT (Smart Logic)
@router.patch("/history/{inv_id}")
def update_payment(inv_id: int, payload: PatchPayment):
    amount = payload.amount
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    col = get_collection("invoices")
    
    # Current state fetch karo
    inv = col.find_one({"inv_id": inv_id})
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Calculations (Backend is source of truth)
    current_paid = float(inv.get("paid", 0))
    total = float(inv.get("total", 0))
    
    new_paid = current_paid + amount
    # Negative due prevent karne ke liye max(0)
    new_due = max(0.0, total - new_paid)
    
    # Auto-Status Update
    new_status = "Paid" if new_due <= 0.5 else "Partial"

    # Log Entry create karo
    log_entry = {
        "date": datetime.now().strftime("%d/%m/%Y, %I:%M %p"),
        "amount": amount,
        "type": "Settlement"
    }

    # Atomic Update using $set and $push
    col.update_one(
        {"inv_id": inv_id},
        {
            "$set": {
                "paid": new_paid, 
                "due": new_due, 
                "status": new_status
            },
            "$push": {"history": log_entry}
        }
    )

    return {"status": "updated", "new_due": new_due, "new_paid": new_paid}

# 6. SETTINGS (Singleton Pattern fetch)
@router.get("/settings", response_model=SettingsSchema)
def get_settings():
    col = get_collection("settings")
    data = col.find_one({}, {"_id": 0})
    if not data:
        # Default return karo agar DB mein kuch nahi hai
        return SettingsSchema().model_dump()
    return data

@router.post("/settings")
def update_settings(sets: SettingsSchema):
    col = get_collection("settings")
    col.update_one({}, {"$set": sets.model_dump()}, upsert=True)
    return {"status": "updated"}