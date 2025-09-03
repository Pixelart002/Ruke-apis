# app/schemas.py
from pydantic import BaseModel, EmailStr
from typing import Optional, List

# Users
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    created_at: str

# Login
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    user_id: int

# Products
class ProductCreate(BaseModel):
    title: str
    description: str
    price: float
    image_url: Optional[str]

class ProductOut(ProductCreate):
    id: int
    created_at: str

# Cart
class CartItemCreate(BaseModel):
    product_id: int
    quantity: int

class CartItemOut(BaseModel):
    id: int
    product_id: int
    quantity: int

# Orders
class OrderCreate(BaseModel):
    cart_items: List[CartItemCreate]
    address: str
    payment_method: str

class OrderOut(BaseModel):
    id: int
    total: float
    status: str