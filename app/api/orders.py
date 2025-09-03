from fastapi import APIRouter, Depends, HTTPException
from app.api.deps import get_current_user, get_admin_user
from app.services.orders_service import checkout_cart
from app.db.supabase import get_client

router = APIRouter()

@router.post("/checkout")
def checkout(user=Depends(get_current_user)):
    try:
        res = checkout_cart(user["id"])
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/my")
def my_orders(user=Depends(get_current_user)):
    client = get_client()
    res = client.table("orders").select("*, order_items(*)").eq("user_id", user["id"]).order("created_at", desc=True).execute()
    return res.data

@router.get("/all")
def all_orders(admin=Depends(get_admin_user)):
    from app.db.supabase import get_client
    res = get_client().table("orders").select("*, order_items(*)").order("created_at", desc=True).execute()
    return res.data
