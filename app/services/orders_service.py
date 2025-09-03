from app.db.supabase import get_client
from decimal import Decimal

def checkout_cart(user_id: str):
    client = get_client()
    carts = client.table("carts").select("*").eq("user_id", user_id).execute()
    if not carts.data:
        raise Exception("Cart not found")
    cart = carts.data[0]
    items_res = client.table("cart_items").select("*, products(*)").eq("cart_id", cart["id"]).execute()
    items = items_res.data or []
    total = Decimal(0)
    order_items = []
    for it in items:
        prod = it.get("products") or {}
        price = Decimal(str(prod.get("price", 0)))
        qty = int(it.get("quantity", 1))
        total += price * qty
        order_items.append({"product_id": prod.get("id"), "quantity": qty, "price": str(price)})
    order = client.table("orders").insert({"user_id": user_id, "total": str(total), "status": "paid"}).execute()
    if order.error:
        raise Exception("Could not create order")
    order_id = order.data[0]["id"]
    # insert order_items
    for oi in order_items:
        client.table("order_items").insert({"order_id": order_id, "product_id": oi["product_id"], "quantity": oi["quantity"], "price": oi["price"]}).execute()
    # clear cart items
    client.table("cart_items").delete().eq("cart_id", cart["id"]).execute()
    return {"order_id": order_id, "total": str(total)}
