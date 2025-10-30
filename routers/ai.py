from fastapi import APIRouter, Depends, HTTPException
import httpx
from typing import Dict

# ✅ FIX: move this import ABOVE any usage of auth_utils
from auth import utils as auth_utils

router = APIRouter(
    prefix="/ai",
    tags=["AI Core"]
)

@router.get("/ask")
async def ask(question: str, current_user: Dict = Depends(auth_utils.get_current_user)):
    try:
        # Extract fullname instead of user_id
        fullname = current_user.get("fullname", "UnknownUser")

        # Build Mistral URL using fullname
        mistral_url = f"https://mistral-ai-three.vercel.app/?id={fullname}&question={question}"

        # Call Mistral endpoint
        async with httpx.AsyncClient() as client:
            res = await client.get(mistral_url, timeout=60)

        return {"fullname": fullname, "reply": res.text}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))