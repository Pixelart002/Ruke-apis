from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, constr, Field
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from auth import utils as auth_utils
from database import db
from bson import ObjectId

router = APIRouter(prefix="/stores", tags=["Decentralized Stores & E-commerce"])

# --- Pydantic Models for Validation (V2 Compatible) ---
class Product(BaseModel):
    name: constr(min_length=3, max_length=50)
    description: Optional[str] = None
    price: float = Field(..., gt=0)
    stock_quantity: int = Field(..., ge=0)
    images: List[str] = []

class StoreCreate(BaseModel):
    name: constr(min_length=3, max_length=50)
    slug: constr(min_length=3, max_length=30, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

class OrderItem(BaseModel):
    product_name: str
    quantity: int
    price: float

class Order(BaseModel):
    id: str = Field(alias="_id")
    store_id: str
    items: List[OrderItem]
    total_amount: float
    customer_email: str
    status: str
    created_at: datetime
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class StorePublic(BaseModel):
    name: str
    slug: str
    products: List[Product] = []
    owner_username: str

class StoreAdmin(StorePublic):
    id: str = Field(alias="_id")
    orders: List[Order] = []
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

# --- API Endpoints (100% SYNCHRONOUS) ---
@router.post("/create", status_code=status.HTTP_201_CREATED)
def create_store(store_data: StoreCreate, current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)):
    if db.stores.find_one({"slug": store_data.slug}):
        raise HTTPException(status_code=409, detail="This store slug is already taken.")
    if db.stores.find_one({"owner_id": ObjectId(current_user["_id"])}):
        raise HTTPException(status_code=400, detail="You have already created a store.")
    
    new_store = {
        "owner_id": ObjectId(current_user["_id"]),
        "owner_username": current_user["username"],
        "name": store_data.name,
        "slug": store_data.slug,
        "products": [],
        "created_at": datetime.now(timezone.utc)
    }
    db.stores.insert_one(new_store)
    return {"message": f"Store '{store_data.name}' created successfully!"}

@router.get("/mystore", response_model=StoreAdmin)
def get_my_store_dashboard(current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)):
    store = db.stores.find_one({"owner_id": ObjectId(current_user["_id"])})
    if not store:
        raise HTTPException(status_code=404, detail="You have not created a store yet.")
    
    orders = list(db.orders.find({"store_id": store["_id"]}).sort("created_at", -1))
    
    store["_id"] = str(store["_id"]) 
    for order in orders:
        order["_id"] = str(order["_id"])
        if 'store_id' in order:
             order['store_id'] = str(order['store_id'])
    
    store['orders'] = orders
    return store

@router.post("/mystore/products", status_code=status.HTTP_201_CREATED)
def add_product_to_store(product: Product, current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)):
    product_data = product.model_dump(by_alias=True) 
    result = db.stores.update_one(
        {"owner_id": ObjectId(current_user["_id"])},
        {"$push": {"products": product_data}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Your store was not found.")
    return {"message": f"Product '{product.name}' added."}

@router.get("/{slug}", response_model=StorePublic)
def get_store_by_slug(slug: str):
    store = db.stores.find_one({"slug": slug})
    if not store:
        raise HTTPException(status_code=404, detail="Store not found.")
    
    store["_id"] = str(store["_id"])
    return store