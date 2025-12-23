from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from slugify import slugify
from bson import ObjectId

# --- LOCAL IMPORTS ---
from database import db
from auth import utils as auth_utils

# Note: Prefix '/store' main.py mein lagega
router = APIRouter(prefix="/store", tags=["E-commerce Store"])

# --- 1. SCHEMAS (Data Models) ---

class StoreCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=50, description="Store Name (e.g. 'My Shop')")
    category: str = Field("General", description="Category like Fashion, Tech, etc.")
    description: Optional[str] = Field(None, max_length=200)

class StoreResponse(BaseModel):
    id: str
    name: str
    slug: str
    store_url: str
    owner_id: str
    is_active: bool
    created_at: datetime

# --- 2. ENDPOINTS ---

@router.post("/create", response_model=StoreResponse)
async def create_store(
    store_data: StoreCreate,
    current_user: dict = Depends(auth_utils.get_current_user)
):
    """
    Creates a new store. 
    Strict Rule: 1 User = 1 Store only.
    """
    user_id = str(current_user["_id"])

    # A. CHECK: Kya user ke paas pehle se store hai?
    existing_store = db.stores.find_one({"owner_id": user_id})
    if existing_store:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already have a store. Multiple stores are not allowed."
        )

    # B. GENERATE SLUG (URL)
    # "Vikram's Shop" -> "vikrams-shop"
    base_slug = slugify(store_data.name)
    slug = base_slug
    counter = 1

    # Check globally if slug is taken by someone else
    while db.stores.find_one({"slug": slug}):
        slug = f"{base_slug}-{counter}"
        counter += 1

    # C. PREPARE STORE OBJECT
    new_store = {
        "owner_id": user_id,
        "owner_name": current_user.get("fullname", "Merchant"),
        "name": store_data.name,
        "slug": slug,
        "category": store_data.category,
        "description": store_data.description,
        "created_at": datetime.utcnow(),
        "is_active": True,
        # Default Theme Settings
        "theme": {
            "primary_color": "#10b981",
            "font": "Inter",
            "layout": "grid"
        }
    }

    # D. SAVE TO DATABASE
    result = db.stores.insert_one(new_store)
    
    # URL Format Update: Points to the public host page
    # Example: /misc/store-host.html?store=shree-balaji-traders
    frontend_url_path = f"/misc/store-host.html?store={slug}"

    # E. RETURN SUCCESS RESPONSE
    return {
        "id": str(result.inserted_id),
        "name": new_store["name"],
        "slug": new_store["slug"],
        "store_url": frontend_url_path, # Updated Path
        "owner_id": user_id,
        "is_active": new_store["is_active"],
        "created_at": new_store["created_at"]
    }

@router.get("/my-store")
async def get_my_store_details(
    current_user: dict = Depends(auth_utils.get_current_user)
):
    """
    Ye endpoint check karta hai ki logged-in user ka koi store hai ya nahi.
    Frontend isse call karke decide karega ki "Create Store" button dikhana hai ya "Dashboard".
    """
    user_id = str(current_user["_id"])
    
    store = db.stores.find_one({"owner_id": user_id})
    
    if not store:
        # 404 ka matlab: User ne abhi tak store nahi banaya (Frontend 'Create' button dikhaye)
        raise HTTPException(status_code=404, detail="No store found for this user.")
    
    # Convert ObjectId to string
    store["id"] = str(store["_id"])

    # Important: Agar database me store_url save nahi hai, to hume yahan calculate karna padega
    # taaki frontend ko hamesha sahi URL mile.
    if "slug" in store:
        store["store_url"] = f"/misc/store-host.html?store={store['slug']}" # Updated Path

    return store