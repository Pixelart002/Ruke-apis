from fastapi import APIRouter, HTTPException
import httpx

router = APIRouter()
NEYNAR_API_KEY = "BA7BE33B-DA56-4F0A-8DF9-2E7DDDC3D6B7"
BASE_URL = "https://api.neynar.com/v2/farcaster"

@router.get("/check_profile/{username}")
async def check_profile(username: str):
    """
    Check user profile data from Neynar API.
    Example: /check_profile/kyro.base.eth
    """
    try:
        url = f"{BASE_URL}/user-by-username?username={username}"
        headers = {"accept": "application/json", "api_key": NEYNAR_API_KEY}

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, headers=headers)

        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch from Neynar")

        data = response.json()
        if "user" not in data:
            raise HTTPException(status_code=404, detail="User not found")

        return {
            "status": "success",
            "username": username,
            "fid": data["user"]["fid"],
            "display_name": data["user"]["display_name"],
            "bio": data["user"].get("bio", "No bio available"),
            "profile_url": f"https://warpcast.com/{username}"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))