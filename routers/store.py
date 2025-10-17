from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, constr, Field, HttpUrl
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from auth import utils as auth_utils
from database import db
from bson import ObjectId

router = APIRouter(prefix="/stores", tags=["Decentralized Stores"])

# --- Pydantic Models for Validation ---
class Product(BaseModel):
    name: constr(min_length=3, max_length=50)
    price: float = Field(..., gt=0)
    image_url: Optional[HttpUrl] = None

class StoreCreate(BaseModel):
    name: constr(min_length=3, max_length=50)
    # Subdomain sirf small letters, numbers, aur hyphens allow karega
    subdomain: constr(
        min_length=3,
        max_length=30,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )

class StorePublic(BaseModel):
    name: str
    subdomain: str
    products: List[Product] = []
    owner_username: str

class StoreAdmin(StorePublic):
    id: str

# --- API Endpoints ---
@router.post("/create", status_code=status.HTTP_201_CREATED)
async def create_store(
    store_data: StoreCreate,
    current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)
):
    existing_subdomain = await db.stores.find_one({"subdomain": store_data.subdomain})
    if existing_subdomain:
        raise HTTPException(
            status_code=409,
            detail="This subdomain is already taken. Please choose another."
        )

    existing_store = await db.stores.find_one({"owner_id": ObjectId(current_user["_id"])})
    if existing_store:
        raise HTTPException(
            status_code=400,
            detail="You have already created a store."
        )

    new_store = {
        "owner_id": ObjectId(current_user["_id"]),
        "owner_username": current_user["username"],
        "name": store_data.name,
        "subdomain": store_data.subdomain,
        "products": [],
        "created_at": datetime.now(timezone.utc),
    }

    await db.stores.insert_one(new_store)
    return {"message": f"Store '{store_data.name}' created successfully!"}


@router.get("/mystore", response_model=StoreAdmin)
async def get_my_store(
    current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)
):
    store = await db.stores.find_one({"owner_id": ObjectId(current_user["_id"])})
    if not store:
        raise HTTPException(status_code=404, detail="You have not created a store yet.")

    store["id"] = str(store["_id"])
    return store


@router.post("/mystore/products", status_code=status.HTTP_201_CREATED)
async def add_product_to_store(
    product: Product,
    current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)
):
    result = await db.stores.update_one(
        {"owner_id": ObjectId(current_user["_id"])},
        {"$push": {"products": product.dict()}}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Your store was not found.")

    return {"message": f"Product '{product.name}' added successfully."}


@router.get("/{subdomain}", response_model=StorePublic)
async def get_store_by_subdomain(subdomain: str):
    store = await db.stores.find_one({"subdomain": subdomain})
    if not store:
        raise HTTPException(status_code=404, detail="Store not found.")
    return store