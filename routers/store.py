from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, constr, Field, HttpUrl
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from auth import utils as auth_utils
from database import db
from bson import ObjectId

router = APIRouter(prefix="/stores", tags=["Decentralized Stores & E-commerce"])

# --- Pydantic Models for Validation (V2 Compatible) ---
class Product(BaseModel):
    name: constr(min_length=3, max_length=50)
    price: float = Field(..., gt=0)
    stock_quantity: int = Field(..., ge=0)
    image_url: Optional[str] = None

class StoreCreate(BaseModel):
    name: constr(min_length=3, max_length=50)
    subdomain: constr(min_length=3, max_length=30, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

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

# --- START: YEH HAI AAPKA LEGENDARY FIX ---
# StorePublic model ko yahan define kiya gaya hai
class StorePublic(BaseModel):
    name: str
    subdomain: str
    products: List[Product] = []
    owner_username: str
# --- END: LEGENDARY FIX ---

class StoreAdmin(StorePublic): # StoreAdmin ab StorePublic se inherit karega
    id: str = Field(alias="_id")
    orders: List[Order] = []
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

# --- API Endpoints ---
@router.post("/create", status_code=status.HTTP_201_CREATED)
async def create_store(store_data: StoreCreate, current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)):
    if await db.stores.find_one({"subdomain": store_data.subdomain}):
        raise HTTPException(status_code=409, detail="This subdomain is already taken.")
    if await db.stores.find_one({"owner_id": ObjectId(current_user["_id"])}):
        raise HTTPException(status_code=400, detail="You have already created a store.")

    new_store = {
        "owner_id": ObjectId(current_user["_id"]),
        "owner_username": current_user["username"],
        "name": store_data.name,
        "subdomain": store_data.subdomain,
        "products": [],
        "created_at": datetime.now(timezone.utc)
    }
    await db.stores.insert_one(new_store)
    return {"message": f"Store '{store_data.name}' created successfully!"}

@router.get("/mystore", response_model=StoreAdmin)
async def get_my_store_dashboard(current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)):
    store = await db.stores.find_one({"owner_id": ObjectId(current_user["_id"])})
    if not store:
        raise HTTPException(status_code=404, detail="You have not created a store yet.")
    
    orders_cursor = db.orders.find({"store_id": store["_id"]}).sort("created_at", -1)
    orders = await orders_cursor.to_list(length=50)
    
    store['orders'] = orders
    return store

@router.post("/mystore/products", status_code=status.HTTP_201_CREATED)
async def add_product_to_store(product: Product, current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)):
    result = await db.stores.update_one(
        {"owner_id": ObjectId(current_user["_id"])},
        {"$push": {"products": product.model_dump(by_alias=True)}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Your store was not found.")
    return {"message": f"Product '{product.name}' added."}

@router.get("/{subdomain}", response_model=StorePublic)
async def get_store_by_subdomain(subdomain: str):
    store = await db.stores.find_one({"subdomain": subdomain})
    if not store:
        raise HTTPException(status_code=404, detail="Store not found.")
    return store

