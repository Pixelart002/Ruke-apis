from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from auth.router import router as auth_router
from routers.users import router as users_router
from routers.ai import router as ai_router

app = FastAPI(
    title="YUKU Protocol API",
    description="Backend services for the YUKU Mission Control interface.",
    version="2.5.0"
)

# --- CORS Middleware ---
# This allows your frontend (on a different domain) to communicate with this API.
# IMPORTANT: For production, you should restrict the origins to your actual frontend URL.
origins = [
    "*"  # Allows all origins for development, be more specific in production
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Allows all methods (GET, POST, etc.)
    allow_headers=["*"], # Allows all headers
)


# --- Include Routers ---
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(ai_router)
# --- Root Endpoint ---
@app.get("/")
def read_root():
    return {"status": "YUKU API is online and operational."}





