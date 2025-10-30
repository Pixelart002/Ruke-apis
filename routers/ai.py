from fastapi import APIRouter, Depends, HTTPException
import httpx, json
from typing import Dict
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

        # Try to parse only the "answer" part from nested JSON
        try:
            data = json.loads(res.text)
            # The "reply" key from your structure contains another JSON string
            inner = json.loads(data.get("reply", "{}"))
            answer = inner.get("answer", "").strip()
        except Exception:
            answer = res.text  # fallback if JSON structure fails

        return {"fullname": fullname, "reply": answer}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))