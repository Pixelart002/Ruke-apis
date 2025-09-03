# app/routes/products.py
from fastapi import APIRouter, UploadFile, File
from app.schemas import ProductCreate, ProductOut
from app.database import insert_product, get_products
from app.utils.supabase_client import supabase

router = APIRouter(prefix="/products", tags=["products"])

@router.post("/", response_model=ProductOut)
async def create_product(product: ProductCreate, image: UploadFile = File(None)):
    image_url = None
    if image:
        file_content = await image.read()
        file_path = f"products/{image.filename}"
        supabase.storage.from_("images").upload(file_path, file_content)
        image_url = f"{supabase.storage.from_('images').get_public_url(file_path)['publicUrl']}"
    resp = insert_product(product.title, product.description, product.price, image_url)
    return resp.data[0]

@router.get("/", response_model=list[ProductOut])
async def list_products():
    resp = get_products()
    return resp.data