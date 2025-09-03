from fastapi import APIRouter, Depends, HTTPException
from app.api.deps import get_admin_user
from app.db.supabase import get_client

router = APIRouter()

@router.get("/stats")
def stats(admin=Depends(get_admin_user)):
    client = get_client()
    users = client.table("users").select("count").execute()  # this will return metadata in supabase client
    products = client.table("products").select("count").execute()
    orders = client.table("orders").select("count").execute()
    return {"users": users.data, "products": products.data, "orders": orders.data}
