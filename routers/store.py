from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, constr, Field, HttpUrl
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from bson import ObjectId

from auth import utils as auth_utils
from database import db

router = APIRouter(prefix="/store", tags=["Ultra Enhanced Store Engine"])

# --- Pydantic Models for Validation ---
class Product(BaseModel):
    id: str = Field(default_factory=lambda: str(ObjectId()))
    name: constr(min_length=3, max_length=50)
    price: float = Field(..., gt=0)
    stock: int = Field(..., ge=0)
    description: Optional[str] = ""
    images: List[str] = []

class Ad(BaseModel):
    id: str = Field(default_factory=lambda: str(ObjectId()))
    title: str
    link: HttpUrl
    impressions: int = 0
    clicks: int = 0

# --- API Endpoints ---

# --- Store Admin Endpoints ---
@router.put("/admin")
def update_store_info(store_data: dict, current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)):
    # This is a placeholder. In a real app, you'd validate store_data.
    db.stores.update_one({"owner_id": ObjectId(current_user["_id"])}, {"$set": store_data})
    return {"message": "Store info updated successfully."}

@router.post("/product/admin")
def add_product(product: Product, current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)):
    product_dict = product.model_dump()
    db.stores.update_one({"owner_id": ObjectId(current_user["_id"])}, {"$push": {"products": product_dict}})
    return {"message": f"Product '{product.name}' added."}

@router.put("/product/admin/{product_id}")
def update_product(product_id: str, product_update: Product, current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)):
    product_dict = product_update.model_dump()
    db.stores.update_one(
        {"owner_id": ObjectId(current_user["_id"]), "products.id": product_id},
        {"$set": {"products.$": product_dict}}
    )
    return {"message": "Product updated."}

@router.delete("/product/admin/{product_id}")
def delete_product(product_id: str, current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)):
    db.stores.update_one(
        {"owner_id": ObjectId(current_user["_id"])},
        {"$pull": {"products": {"id": product_id}}}
    )
    return {"message": "Product deleted."}