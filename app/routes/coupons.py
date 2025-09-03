# app/routes/coupons.py
from fastapi import APIRouter
from app.utils.supabase_client import supabase

router = APIRouter(prefix="/coupons", tags=["coupons"])

@router.get("/{code}")
async def get_coupon(code: str):
    resp = supabase.table("coupons").select("*").eq("code", code).execute()
    if not resp.data:
        return {"valid": False}
    return {"valid": True, "discount": resp.data[0]["discount"]}