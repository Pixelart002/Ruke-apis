from fastapi import APIRouter, Depends, HTTPException, status, Form, UploadFile, File
from pydantic import BaseModel, constr, Field, HttpUrl
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from bson import ObjectId
import uuid
import os
import shutil

from auth import utils as auth_utils
from database import db

router = APIRouter(prefix="/store", tags=["Ultra Enhanced Store Engine"])

# --- File Upload Setup ---
UPLOAD_DIR = "public/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def save_upload_file(upload_file: UploadFile) -> str:
    filename = f"{uuid.uuid4().hex}_{upload_file.filename}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)
    # Assuming 'public' is the static directory
    return f"/uploads/{filename}" 

# --- Pydantic Models ---
class Product(BaseModel):
    id: str = Field(default_factory=lambda: str(ObjectId()))
    name: str
    description: str
    price: float
    stock: int
    category: str
    image_url: Optional[str] = None

class Ad(BaseModel):
    id: str = Field(default_factory=lambda: str(ObjectId()))
    brand_name: str
    image_url: Optional[HttpUrl]
    target_url: HttpUrl
    start_date: datetime
    end_date: datetime
    impressions: int = 0
    clicks: int = 0

class Store(BaseModel):
    owner_id: ObjectId
    products: List[Product] = []
    ads: List[Ad] = []
    webpush_subscriptions: List[Any] = [] # Storing webpush subs

    class Config:
        arbitrary_types_allowed = True

# --- API Endpoints ---
def get_user_store(user_id: ObjectId):
    store = db.stores.find_one({"owner_id": user_id})
    if not store:
        # Create a default store if it doesn't exist
        new_store = Store(owner_id=user_id).model_dump()
        db.stores.insert_one(new_store)
        return new_store
    return store

@router.post("/product/admin")
def add_product(
    name: str = Form(...),
    description: str = Form(...),
    price: float = Form(...),
    stock: int = Form(...),
    category: str = Form("general"),
    image: Optional[UploadFile] = File(None),
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    user_id = ObjectId(current_user["_id"])
    product_data = Product(name=name, description=description, price=price, stock=stock, category=category)
    if image:
        product_data.image_url = save_upload_file(image)
    
    db.stores.update_one(
        {"owner_id": user_id},
        {"$push": {"products": product_data.model_dump()}},
        upsert=True
    )
    return {"message": f"Product '{name}' added."}

@router.put("/product/admin/{product_id}")
def update_product(product_id: str, product_update: Product, current_user: Dict = Depends(auth_utils.get_current_user)):
    db.stores.update_one(
        {"owner_id": ObjectId(current_user["_id"]), "products.id": product_id},
        {"$set": {"products.$": product_update.model_dump()}}
    )
    return {"message": "Product updated."}

@router.delete("/product/admin/{product_id}")
def delete_product(product_id: str, current_user: Dict = Depends(auth_utils.get_current_user)):
    db.stores.update_one(
        {"owner_id": ObjectId(current_user["_id"])},
        {"$pull": {"products": {"id": product_id}}}
    )
    return {"message": "Product deleted."}

@router.get("/admin")
def get_store_admin_data(current_user: Dict = Depends(auth_utils.get_current_user)):
    store = get_user_store(ObjectId(current_user["_id"]))
    store["_id"] = str(store["_id"])
    store["owner_id"] = str(store["owner_id"])
    return store
```

---
### ## Step 2: Frontend - Naye Pages Banayein

Ab hum user ko store banane aur manage karne ke liye professional UI banayenge.

#### **A. Sidebar Mein Link Add Karein (`js/main.js`)**
Apni `js/main.js` file ke andar, `renderInitialHTML` function mein, sidebar ke `<nav>` section mein "FEEDBACK" ke baad yeh naya link add karein.

```javascript
// Is line ko main.js ke renderInitialHTML function ke andar, 'feedback' link ke baad daalein
<a href="#" class="nav-link flex items-center p-3 rounded-md" data-page="store">
    <svg class="h-5 w-5 mr-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" /></svg>
    MY STORE
</a>

