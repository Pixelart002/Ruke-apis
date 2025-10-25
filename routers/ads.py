from fastapi import APIRouter, Depends, HTTPException, status, Form, UploadFile, File
from pydantic import BaseModel, HttpUrl, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId
import uuid, os, shutil

from database import db
from auth import utils as auth_utils

router = APIRouter(prefix="/store", tags=["Ultra Enhanced Store Ads"])

# --- File Upload Setup ---
UPLOAD_DIR = "public/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def save_upload_file(upload_file: UploadFile) -> str:
    filename = f"{uuid.uuid4().hex}_{upload_file.filename}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)
    return f"/uploads/{filename}"

# --- Pydantic Ad Model ---
class Ad(BaseModel):
    id: str = Field(default_factory=lambda: str(ObjectId()))
    brand_name: str
    image_url: Optional[str]  # Fixed: HttpUrl -> str
    target_url: str            # Fixed: HttpUrl -> str
    start_date: datetime
    end_date: datetime
    impressions: int = 0
    clicks: int = 0

# --- Helper to get existing store only ---
def get_user_store(user_id: ObjectId):
    store = db.stores.find_one({"owner_id": user_id})
    if not store:
        raise HTTPException(status_code=404, detail="Store not found.")
    return store

# --- CRUD Endpoints for Ads ---

@router.post("/ad/admin")
def add_ad(
    brand_name: str = Form(...),
    target_url: str = Form(...),
    start_date: datetime = Form(...),
    end_date: datetime = Form(...),
    image: Optional[UploadFile] = File(None),
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    """Add new ad (owner only)"""
    user_id = ObjectId(current_user["_id"])
    store = get_user_store(user_id)

    image_url = save_upload_file(image) if image else None
    ad_data = Ad(
        brand_name=brand_name,
        image_url=image_url,
        target_url=str(target_url),
        start_date=start_date,
        end_date=end_date
    )

    db.stores.update_one(
        {"owner_id": user_id},
        {"$push": {"ads": ad_data.dict()}}  # Fixed: model_dump() -> dict()
    )
    return {"message": f"Ad '{brand_name}' added."}

@router.put("/ad/admin/{ad_id}")
def update_ad(
    ad_id: str,
    ad_update: Ad,
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    """Update ad (owner only)"""
    user_id = ObjectId(current_user["_id"])
    store = get_user_store(user_id)

    result = db.stores.update_one(
        {"owner_id": user_id, "ads.id": ad_id},
        {"$set": {"ads.$": ad_update.dict()}}  # Fixed
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Ad not found.")
    return {"message": "Ad updated successfully."}

@router.delete("/ad/admin/{ad_id}")
def delete_ad(
    ad_id: str,
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    """Delete ad (owner only)"""
    user_id = ObjectId(current_user["_id"])
    store = get_user_store(user_id)

    result = db.stores.update_one(
        {"owner_id": user_id},
        {"$pull": {"ads": {"id": ad_id}}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Ad not found.")
    return {"message": "Ad deleted successfully."}

@router.get("/ad/admin")
def list_ads(current_user: Dict = Depends(auth_utils.get_current_user)):
    """List all ads of owner"""
    user_id = ObjectId(current_user["_id"])
    store = get_user_store(user_id)
    ads = store.get("ads", [])
    return {"ads": ads}

@router.post("/ad/view/{ad_id}")
def track_ad_view(ad_id: str):
    """Increment impression count"""
    result = db.stores.update_one(
        {"ads.id": ad_id},
        {"$inc": {"ads.$.impressions": 1}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Ad not found.")
    return {"message": "Impression recorded."}

@router.post("/ad/click/{ad_id}")
def track_ad_click(ad_id: str):
    """Increment click count"""
    result = db.stores.update_one(
        {"ads.id": ad_id},
        {"$inc": {"ads.$.clicks": 1}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Ad not found.")
    return {"message": "Click recorded."}