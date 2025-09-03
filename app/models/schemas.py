from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from uuid import UUID

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3)
    email: EmailStr
    password: str = Field(..., min_length=6)

class UserOut(BaseModel):
    id: UUID
    username: str
    email: EmailStr
    is_admin: bool = False

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class ProductIn(BaseModel):
    title: str
    description: Optional[str] = None
    price: float
    image_url: Optional[str] = None

class ProductOut(ProductIn):
    id: UUID

class CartItemIn(BaseModel):
    product_id: UUID
    quantity: int = 1

class OrderCreate(BaseModel):
    payment_method: Optional[str] = None
