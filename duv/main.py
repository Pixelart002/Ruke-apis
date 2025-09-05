from fastapi import FastAPI, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from app.schemas import User, Product, Order
from app.crud import create_user, get_user_by_email, add_product, list_products, create_order
from app.utils import generate_invoice_pdf, validate_coupon

app = FastAPI(title="GodMode E-Commerce API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.post("/auth/register")
def register(user: User):
    if get_user_by_email(user.email):
        raise HTTPException(status_code=400, detail="Email already exists")
    user_id = create_user(user.dict())
    return {"user_id": str(user_id)}

@app.get("/products")
def get_products():
    return list_products()

@app.post("/products")
def create_product(product: Product):
    pid = add_product(product.dict())
    return {"product_id": str(pid)}

@app.post("/orders")
def place_order(order: Order):
    # Calculate total and apply coupon
    total = order.total_price
    if order.coupon_code:
        total -= validate_coupon(order.coupon_code, total)
    order_dict = order.dict()
    order_dict['total_price'] = total
    oid = create_order(order_dict)
    # Generate invoice
    invoice_file = generate_invoice_pdf(order_dict, {"name": "Demo User", "email": "demo@example.com"}, str(oid))
    return {"order_id": str(oid), "invoice": invoice_file}

@app.get("/invoice/{filename}")
def get_invoice(filename: str):
    return FileResponse(f"invoices/{filename}.pdf")