from fastapi import APIRouter, HTTPException
from database import db_ping
import httpx
from datetime import datetime, timezone
import os

router = APIRouter(prefix="/status", tags=["System Status"])

# --- NEW: Added Backend URL ---
# Hum isse environment variable se lene ki koshish karenge, taaki future mein aasaani ho
BACKEND_URL = os.getenv("BACKEND_URL", "https://open-feliza-pixelart002-78fb4fe8.koyeb.app")
FRONTEND_URL = "https://yuku-nine.vercel.app"

@router.get("/")
async def get_system_status():
    """
    Checks the live status of all project services: Backend, Database, and Frontend.
    """
    backend_status = "Operational"
    
    try:
        if await db_ping():
            db_status = "Connected"
        else:
            db_status = "Unreachable"
            backend_status = "Degraded"
    except Exception:
        db_status = "Unreachable"
        backend_status = "Degraded"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(FRONTEND_URL, timeout=10.0)
            frontend_status = "Operational" if response.status_code == 200 else "Degraded"
    except Exception:
        frontend_status = "Unreachable"

    return {
        "backend_service": {
            "status": backend_status,
            "database": db_status,
            "url": BACKEND_URL,  # --- NEW: Added backend URL to the response ---
            "timestamp": datetime.now(timezone.utc).isoformat()
        },
        "frontend_service": {
            "status": frontend_status,
            "url": FRONTEND_URL
        }
    }

