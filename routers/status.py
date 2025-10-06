from fastapi import APIRouter, HTTPException
from database import db_ping  # Maan rahe hain ki database.py mein ek ping function hai
import httpx
from datetime import datetime, timezone

router = APIRouter(prefix="/status", tags=["System Status"])

FRONTEND_URL = "https://yuku-nine.vercel.app"

@router.get("/")
async def get_system_status():
    """
    Checks the live status of all project services: Backend, Database, and Frontend.
    """
    # 1. Check Backend Status (agar yeh chal raha hai, to backend up hai)
    backend_status = "Operational"
    
    # 2. Check Database Connection
    try:
        await db_ping()
        db_status = "Connected"
    except Exception:
        db_status = "Unreachable"
        backend_status = "Degraded" # Agar DB down hai, to backend poori tarah se operational nahi hai

    # 3. Check Frontend Status
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(FRONTEND_URL, timeout=10.0)
            if response.status_code == 200:
                frontend_status = "Operational"
            else:
                frontend_status = "Degraded"
    except (httpx.ConnectError, httpx.TimeoutException):
        frontend_status = "Unreachable"

    return {
        "backend_service": {
            "status": backend_status,
            "database": db_status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        },
        "frontend_service": {
            "status": frontend_status,
            "url": FRONTEND_URL
        }
    }
    

C. `database.py` ko Update Karein:**
Apni `database.py` file mein yeh `db_ping` function add karein.
```python
async def db_ping():
    # PyMongo mein ping command a-synchronous hota hai
    await client.admin.command('ping')
```

**D. `main.py` Mein Router Add Karein:**
Apni `main.py` file mein naye status router ko import aur include karein.
```python
# main.py mein imports ke saath add karein
from routers.status import router as status_router

# ... (baaki routers ke saath)
app.include_router(status_router)
