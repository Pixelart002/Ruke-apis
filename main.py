# File: main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from auth.router import router as auth_router
from routers.users import router as users_router
from routers.ai import router as ai_router
from routers.notifications import router as notifications_router
from routers.feedback import router as feedback_router







app = FastAPI(
    title="YUKU Protocol API",
    description="Backend services for the YUKU Mission Control interface.",
    version="3.9.5"
)


# --- CORS Middleware ---
origins = ["*"] # For production, change "*" to your frontend's URL

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Include Routers ---
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(ai_router)
app.include_router(notifications_router)
app.include_router(feedback_router)


# --- Root Endpoint ---
@app.get("/")
def read_root():
    return {"status": "YUKU API is online and operational."}