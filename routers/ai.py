from fastapi import APIRouter, Depends
import httpx
from typing import Dict
from your_module import auth_utils  # adjust to your actual path

router = APIRouter()

@router.get("/ask")
async def ask(question: str, current_user: Dict = Depends(auth_utils.get_current_user)):
    try:
        # Extract fullname instead of user_id
        fullname = current_user["fullname"]

        # Build Mistral URL using fullname
        mistral_url = f"https://mistral-ai-three.vercel.app/?id={fullname}&question={question}"

        # Call Mistral endpoint
        async with httpx.AsyncClient() as client:
            res = await client.get(mistral_url, timeout=60)

        return {"fullname": fullname, "reply": res.text}

    except Exception as e:
        return {"error": str(e)}