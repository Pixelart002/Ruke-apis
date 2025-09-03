# app/routes/orders.py
from fastapi import APIRouter
from app.schemas import OrderCreate, OrderOut
from app.utils.supabase_client import supabase

router = APIRouter(prefix="/orders", tags=["orders"])

@router.post("/", response_model=OrderOut)
async def create_order(order: OrderCreate):
    # Calculate total
    total = 0
    for item in order.cart_items:
        prod_resp = supabase.table("products").select("*").eq("id", item.product_id).execute()
        product = prod_resp.data[0]
        total += product["price"] * item.quantity
        # Save each cart item to order_items
        supabase.table("order_items").insert({
            "product_id": item.product_id,
            "quantity": item.quantity
        }).execute()
    resp = supabase.table("orders").insert({
        "total": total,
        "status": "pending",
        "address": order.address,
        "payment_method": order.payment_method
    }).execute()
    return resp.data[0]

@router.get("/", response_model=list[OrderOut])
async def list_orders():
    resp = supabase.table("orders").select("*").execute()
    return resp.data