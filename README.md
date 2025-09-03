# Ruke E-Store Backend — Final Scaffold

**What this is:** a complete FastAPI backend scaffold for an e-store using Supabase as the database and auth store.
It includes JWT authentication, role-based access for admin APIs, Product/Catalog endpoints, Cart and Orders, file layout, Dockerfile, tests, and deployment notes for Koyeb.

**Important:** This project ships with `.env.example` only. Do **NOT** commit real secrets. Replace placeholders with your real values in a local `.env` file (or use Koyeb secret/env UI).

## Quick start (local)
1. Copy `.env.example` to `.env` and fill values.
2. Create virtualenv & install:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Run the app:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
4. API docs: http://localhost:8000/docs

## Layout
- app/main.py — app entrypoint
- app/core — config & utilities (CORS, security)
- app/db — supabase client wrapper & helpers
- app/models — pydantic schemas
- app/api — routers: auth, users, products, cart, orders, admin
- app/services — business logic for orders/cart/products
- tests — pytest tests

## Deploy
- Backend: Build Docker image and deploy on Koyeb using the generated Dockerfile.
- Frontend: Use Vercel (not included in this backend scaffold)

## Supabase Notes
- This scaffold uses Supabase as the DB through `supabase-py` client.
- You should have tables: users, products, carts, cart_items, orders, order_items. Example SQL is included in `supabase_schema.sql`.

## Security & Hints
- Rotate Supabase service keys and avoid embedding keys in code.
- Use HTTPS and configure CORS origins in production.
- Use Koyeb environment secrets to store SUPABASE_ and SECRET_KEY values.
