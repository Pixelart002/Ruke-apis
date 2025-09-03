from fastapi import APIRouter, Depends, HTTPException
from app.models.schemas import ProductIn, ProductOut
from app.db.supabase import get_client
from typing import List
from app.api.deps import get_admin_user

router = APIRouter()

@router.get("/", response_model=List[ProductOut])
def list_products():
    client = get_client()
    res = client.table("products").select("*").order("created_at", desc=True).execute()
    if res.error:
        raise HTTPException(status_code=500, detail="DB error")
    return res.data

@router.post("/", response_model=ProductOut)
def create_product(payload: ProductIn, admin=Depends(get_admin_user)):
    client = get_client()
    ins = client.table("products").insert(payload.dict()).execute()
    if ins.error:
        raise HTTPException(status_code=500, detail="DB error")
    return ins.data[0]

@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: str):
    client = get_client()
    res = client.table("products").select("*").eq("id", product_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Not found")
    return res.data[0]

@router.delete("/{product_id}")
def delete_product(product_id: str, admin=Depends(get_admin_user)):
    client = get_client()
    res = client.table("products").delete().eq("id", product_id).execute()
    if res.error:
        raise HTTPException(status_code=500, detail="DB error")
    return {"deleted": True}
