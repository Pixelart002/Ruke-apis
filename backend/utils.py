import pdfkit
from datetime import datetime
import os
from bson import ObjectId
from fastapi import HTTPException
from .models import coupons_col

def generate_invoice_pdf(order, user, filename):
    html = f"""
    <h1>Invoice #{order['_id']}</h1>
    <p>Name: {user['name']}</p>
    <p>Email: {user['email']}</p>
    <p>Shipping Address: {order['shipping_address']}</p>
    <table border="1" style="width:100%;border-collapse: collapse;">
    <tr><th>Product</th><th>Quantity</th><th>Price</th></tr>
    """
    for item in order['items']:
        html += f"<tr><td>{item['product_name']}</td><td>{item['quantity']}</td><td>{item['price']}</td></tr>"
    html += f"</table><p>Total: {order['total_price']}</p>"
    os.makedirs("invoices", exist_ok=True)
    pdf_path = f"invoices/{filename}.pdf"
    pdfkit.from_string(html, pdf_path)
    return pdf_path

def validate_coupon(code, total_price):
    coupon = coupons_col.find_one({"code": code, "active": True})
    if not coupon:
        raise HTTPException(status_code=400, detail="Invalid coupon")
    now = datetime.now()
    if coupon['valid_from'] > now or coupon['valid_until'] < now:
        raise HTTPException(status_code=400, detail="Coupon expired")
    if total_price < coupon['min_order_value']:
        raise HTTPException(status_code=400, detail="Minimum order value not met")
    discount = coupon['discount_value']
    if coupon['discount_type'] == "percentage":
        return total_price * (discount / 100)
    return discount