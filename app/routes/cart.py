# app/routes/cart.py
from fastapi import APIRouter, Depends
from app.schemas import CartItemCreate, CartItemOut
from app.utils.supabase_client import supabase

router = APIRouter(prefix="/cart", tags=["cart"])

@router.post("/", response_model=CartItemOut)
async def add_to_cart(item: CartItemCreate):
    resp = supabase.table("cart").insert({
        "product_id": item.product_id,
        "quantity": item.quantity
    }).execute()
    return resp.data[0]

@router.get("/", response_model=list[CartItemOut])
async def list_cart_items():
    resp = supabase.table("cart").select("*").execute()
    return resp.data