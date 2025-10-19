# routers/store.py
from fastapi import APIRouter, Depends, HTTPException, Form, UploadFile, File
from typing import Dict, Any, Optional, List
from pydantic import BaseModel
from datetime import datetime, timezone
from bson import ObjectId
import uuid
import os
import qrcode
from io import BytesIO
import base64
import shutil

from auth import utils as auth_utils
from database import db

router = APIRouter(prefix="/store", tags=["Vendor Store"])

# --- MongoDB Collections ---
product_collection = db["products"]
order_collection = db["orders"]
discount_collection = db["discounts"]
ads_collection = db["ads"]
catalog_collection = db["catalogs"]

# --- Schemas ---
class ProductCreate(BaseModel):
    name: str
    description: str
    price: float
    stock: int
    category: Optional[str] = "general"
    image_url: Optional[str] = None

class ProductUpdate(ProductCreate):
    pass

class OrderCreate(BaseModel):
    products: List[Dict[str, Any]]  # [{"product_id": "", "quantity": 2}]
    customer_name: str
    customer_email: str
    customer_phone: str
    address: str

class OrderStatusUpdate(BaseModel):
    status: str  # Pending, Shipped, Delivered, Cancelled

class DiscountCreate(BaseModel):
    code: str
    percentage: float
    valid_until: Optional[datetime] = None

class AdCreate(BaseModel):
    brand_name: str
    image_url: Optional[str]
    target_url: Optional[str]
    start_date: datetime
    end_date: datetime

class NotificationRequest(BaseModel):
    title: str
    body: str

# --- Helper for file uploads ---
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def save_upload_file(upload_file: UploadFile, destination: str) -> str:
    file_path = os.path.join(UPLOAD_DIR, destination)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)
    return f"/{file_path}"  # path relative to server root

# --- Product CRUD ---
@router.post("/products")
async def add_product(
    name: str = Form(...),
    description: str = Form(...),
    price: float = Form(...),
    stock: int = Form(...),
    category: str = Form("general"),
    image: Optional[UploadFile] = File(None),
    image_url: Optional[str] = Form(None),
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    product_data = {
        "name": name,
        "description": description,
        "price": price,
        "stock": stock,
        "category": category,
        "vendor_id": str(current_user["_id"]),
        "created_at": datetime.now(timezone.utc)
    }

    # Handle file upload or image_url
    if image:
        filename = f"{uuid.uuid4().hex}_{image.filename}"
        uploaded_path = save_upload_file(image, filename)
        product_data["image_url"] = uploaded_path
    elif image_url:
        product_data["image_url"] = image_url

    result = product_collection.insert_one(product_data)
    return {"message": "Product added successfully", "product_id": str(result.inserted_id)}

@router.put("/products/{product_id}")
async def update_product(
    product_id: str,
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    price: Optional[float] = Form(None),
    stock: Optional[int] = Form(None),
    category: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    image_url: Optional[str] = Form(None),
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    product = product_collection.find_one({"_id": ObjectId(product_id), "vendor_id": str(current_user["_id"])})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found or not your product")

    update_data = {}
    if name is not None: update_data["name"] = name
    if description is not None: update_data["description"] = description
    if price is not None: update_data["price"] = price
    if stock is not None: update_data["stock"] = stock
    if category is not None: update_data["category"] = category

    if image:
        filename = f"{uuid.uuid4().hex}_{image.filename}"
        update_data["image_url"] = save_upload_file(image, filename)
    elif image_url:
        update_data["image_url"] = image_url

    if update_data:
        product_collection.update_one({"_id": ObjectId(product_id)}, {"$set": update_data})

    return {"message": "Product updated successfully"}

@router.get("/products")
async def list_products():
    products = list(product_collection.find({}))
    for p in products: p["_id"] = str(p["_id"])
    return products

@router.get("/products/{product_id}")
async def get_product(product_id: str):
    product = product_collection.find_one({"_id": ObjectId(product_id)})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product["_id"] = str(product["_id"])
    return product

@router.delete("/products/{product_id}")
async def delete_product(product_id: str, current_user: Dict = Depends(auth_utils.get_current_user)):
    product = product_collection.find_one({"_id": ObjectId(product_id), "vendor_id": str(current_user["_id"])})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found or not your product")
    product_collection.delete_one({"_id": ObjectId(product_id)})
    return {"message": "Product deleted successfully"}

# --- Orders ---
@router.post("/orders")
async def create_order(order: OrderCreate):
    order_data = order.dict()
    order_data["status"] = "Pending"
    order_data["created_at"] = datetime.now(timezone.utc)
    result = order_collection.insert_one(order_data)
    return {"message": "Order placed successfully", "order_id": str(result.inserted_id)}

@router.get("/orders")
async def list_orders(current_user: Dict = Depends(auth_utils.get_current_user)):
    orders = list(order_collection.find({"vendor_id": str(current_user["_id"])}))
    for o in orders: o["_id"] = str(o["_id"])
    return orders

@router.get("/orders/{order_id}")
async def get_order(order_id: str, current_user: Dict = Depends(auth_utils.get_current_user)):
    order = order_collection.find_one({"_id": ObjectId(order_id)})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    order["_id"] = str(order["_id"])
    return order

@router.post("/orders/{order_id}/update-status")
async def update_order_status(order_id: str, status_update: OrderStatusUpdate, current_user: Dict = Depends(auth_utils.get_current_user)):
    order = order_collection.find_one({"_id": ObjectId(order_id)})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    order_collection.update_one({"_id": ObjectId(order_id)}, {"$set": {"status": status_update.status}})
    return {"message": f"Order status updated to {status_update.status}"}

# --- Billing & QR Codes ---
@router.post("/orders/{order_id}/generate-bill")
async def generate_bill(order_id: str):
    order = order_collection.find_one({"_id": ObjectId(order_id)})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    qr = qrcode.QRCode(box_size=4, border=2)
    qr.add_data(f"OrderID:{order_id}")
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    qr_base64 = base64.b64encode(buffered.getvalue()).decode()

    return {
        "order_id": order_id,
        "customer_name": order["customer_name"],
        "products": order["products"],
        "status": order["status"],
        "qr_code_base64": qr_base64
    }

# --- Discounts ---
@router.post("/discounts")
async def add_discount(discount: DiscountCreate):
    discount_collection.insert_one(discount.dict())
    return {"message": "Discount added successfully"}

@router.get("/discounts")
async def list_discounts():
    discounts = list(discount_collection.find({}))
    for d in discounts: d["_id"] = str(d["_id"])
    return discounts

@router.delete("/discounts/{discount_id}")
async def delete_discount(discount_id: str):
    discount_collection.delete_one({"_id": ObjectId(discount_id)})
    return {"message": "Discount deleted successfully"}

# --- Catalogs ---
@router.get("/catalog")
async def get_catalog():
    catalog_items = list(product_collection.find({}))
    for c in catalog_items: c["_id"] = str(c["_id"])
    return {"catalog": catalog_items}

@router.post("/catalog/share")
async def share_catalog():
    slug = str(uuid.uuid4())
    catalog_collection.insert_one({"slug": slug, "created_at": datetime.now(timezone.utc)})
    catalog_url = f"https://open-feliza-pixelart002-78fb4fe8.koyeb.app/store/catalog/shared/{slug}"
    return {"catalog_url": catalog_url}

# --- Ads ---
@router.post("/ads")
async def create_ad(ad: AdCreate):
    ads_collection.insert_one(ad.dict())
    return {"message": "Ad created successfully"}

@router.get("/ads")
async def list_ads():
    ads = list(ads_collection.find({}))
    for a in ads: a["_id"] = str(a["_id"])
    return ads

# --- Notifications ---
@router.post("/notify")
async def send_notification(notification: NotificationRequest):
    # Placeholder: integrate with push notification logic
    return {"message": "Notification sent (placeholder)", "title": notification.title}