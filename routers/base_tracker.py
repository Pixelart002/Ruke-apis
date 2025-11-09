from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import httpx, json

router = APIRouter(
    prefix="/base",
    tags=["Base Tracker"]
)

NEYMAR_API_KEY = "BA7BE33B-DA56-4F0A-8DF9-2E7DDDC3D6B7"
NEYMAR_BASE_URL = "https://api.neynar.com/v2/farcaster"

# ------------------ Utility ------------------ #
def clean_surrogates(text: str) -> str:
    """Ensures text is valid UTF-8."""
    if not isinstance(text, str):
        text = str(text)
    return text.encode("utf-8", "surrogatepass").decode("utf-8", "ignore")

# ------------------ CHECK Endpoint ------------------ #
@router.get("/check")
async def check_script():
    """
    GET /base/check
    Tests if Neynar API connection is working.
    """
    try:
        headers = {
            "accept": "application/json",
            "api_key": NEYMAR_API_KEY
        }

        test_url = f"{NEYMAR_BASE_URL}/user-by-username?username=iamkyro"  # example username
        async with httpx.AsyncClient() as client:
            res = await client.get(test_url, headers=headers, timeout=30)

        if res.status_code != 200:
            raise HTTPException(status_code=res.status_code, detail="Neynar API not responding properly")

        data = res.json()
        username = data.get("result", {}).get("user", {}).get("username", "unknown")
        fid = data.get("result", {}).get("user", {}).get("fid", "N/A")

        return JSONResponse(
            content={
                "status": "✅ Neynar API Connected Successfully",
                "checked_user": username,
                "fid": fid
            },
            ensure_ascii=False
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Check failed: {str(e)}")