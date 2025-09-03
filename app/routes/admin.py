# app/routes/admin.py
from fastapi import APIRouter
from app.utils.supabase_client import supabase

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/users")
async def list_users():
    resp = supabase.table("users").select("*").execute()
    return resp.data

@router.get("/products")
async def list_products():
    resp = supabase.table("products").select("*").execute()
    return resp.data