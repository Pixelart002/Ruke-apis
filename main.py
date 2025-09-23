# File: main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from auth.router import router as auth_router
from routers.users import router as users_router
from routers.ai import router as ai_router
from routers.notifications import router as notifications_router

import firebase_admin
from firebase_admin import credentials
import os
import json

app = FastAPI(
    title="YUKU Protocol API",
    description="Backend services for the YUKU Mission Control interface.",
    version="2.5.0"
)

# --- Firebase Initialization (Works Everywhere) ---
FIREBASE_KEY_FILENAME = "yukuprotocol01-firebase-adminsdk-fbsvc-1ac73f33b3.json"

try:
    firebase_creds_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
    if firebase_creds_json:
        print("Initializing Firebase from Environment Variable (Deployment Mode)...")
        creds_dict = json.loads(firebase_creds_json)
        cred = credentials.Certificate(creds_dict)
    elif os.path.exists(FIREBASE_KEY_FILENAME):
        print(f"Initializing Firebase from local file: '{FIREBASE_KEY_FILENAME}' (Local Mode)...")
        cred = credentials.Certificate(FIREBASE_KEY_FILENAME)
    else:
        raise FileNotFoundError("Firebase credentials not found.")

    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    
    print("✅ Firebase Admin SDK initialized successfully.")

except Exception as e:
    print(f"❌ Error initializing Firebase Admin SDK: {e}")
# ----------------------------------------------------

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

# --- Root Endpoint ---
@app.get("/")
def read_root():
    return {"status": "YUKU API is online and operational."}