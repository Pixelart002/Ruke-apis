from fastapi import APIRouter, Depends, HTTPException
from app.api.deps import get_current_user
from app.models.schemas import CartItemIn
from app.db.supabase import get_client

router = APIRouter()

@router.post("/add")
def add_to_cart(item: CartItemIn, user=Depends(get_current_user)):
    client = get_client()
    # find or create cart for user
    carts = client.table("carts").select("*").eq("user_id", user["id"]).execute()
    if carts.data and len(carts.data)>0:
        cart = carts.data[0]
    else:
        ins = client.table("carts").insert({"user_id": user["id"]}).execute()
        cart = ins.data[0]
    # upsert cart item (simple approach: insert new row)
    ci = client.table("cart_items").insert({"cart_id": cart["id"], "product_id": item.product_id, "quantity": item.quantity}).execute()
    if ci.error:
        raise HTTPException(status_code=500, detail="Could not add item")
    return {"cart_id": cart["id"], "item": ci.data[0]}

@router.get("/", response_model=list)
def get_cart(user=Depends(get_current_user)):
    client = get_client()
    carts = client.table("carts").select("*").eq("user_id", user["id"]).execute()
    if not carts.data:
        return {"items": []}
    cart = carts.data[0]
    items = client.table("cart_items").select("*, products(*)").eq("cart_id", cart["id"]).execute()
    return {"cart": cart, "items": items.data}

@router.post("/remove")
def remove_item(payload: dict, user=Depends(get_current_user)):
    item_id = payload.get("item_id")
    if not item_id:
        raise HTTPException(status_code=400, detail="item_id required")
    client = get_client()
    res = client.table("cart_items").delete().eq("id", item_id).execute()
    if res.error:
        raise HTTPException(status_code=500, detail="Could not remove")
    return {"removed": True}
