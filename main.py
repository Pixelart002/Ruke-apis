from fastapi import FastAPI
from routes import auth, profile, admin, ai
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Ruké Profile API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Routers
app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(admin.router)
app.include_router(ai.router)