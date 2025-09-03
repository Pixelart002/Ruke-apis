# app/main.py
from fastapi import FastAPI
from app.routes import users, products, cart, orders, payments, coupons, admin

app = FastAPI(title="Ruke Backend")

# Include routers
app.include_router(users.router)
app.include_router(products.router)
app.include_router(cart.router)
app.include_router(orders.router)
app.include_router(payments.router)
app.include_router(coupons.router)
app.include_router(admin.router)

@app.get("/")
async def root():
    return {"message": "Ruke Backend is running!"}