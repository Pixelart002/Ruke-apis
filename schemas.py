from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime

class User(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str = "customer"

class Product(BaseModel):
    category: str
    model: str
    size: Optional[str] = None
    material: Optional[str] = None
    finish: Optional[str] = None
    price: float
    images: Optional[List[str]] = []

class OrderItem(BaseModel):
    product_id: str
    quantity: int
    price: float

class Order(BaseModel):
    user_id: str
    items: List[OrderItem]
    total_price: float
    coupon_code: Optional[str] = None
    shipping_address: str
    status: str = "Pending"