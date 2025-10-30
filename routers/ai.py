from fastapi import APIRouter, Depends, HTTPException
import httpx, json, re
from typing import Dict
from auth import utils as auth_utils

router = APIRouter(
    prefix="/ai",
    tags=["AI Core"]
)

@router.get("/ask")
async def ask(question: str, current_user: Dict = Depends(auth_utils.get_current_user)):
    try:
        fullname = current_user.get("fullname", "UnknownUser")
        mistral_url = f"https://mistral-ai-three.vercel.app/?id={fullname}&question={question}"

        async with httpx.AsyncClient() as client:
            res = await client.get(mistral_url, timeout=60)

        # Try to extract the "answer" part using regex (works even if nested JSON is stringified)
        match = re.search(r'"answer"\s*:\s*"([^"]+)"', res.text)
        if match:
            # Clean escaped sequences like \\u2019, \\n, etc.
            raw_answer = match.group(1)
            clean_answer = bytes(raw_answer, "utf-8").decode("unicode_escape").replace("\\n", "\n").strip()
        else:
            clean_answer = "No valid answer found."

        return {"fullname": fullname, "reply": clean_answer}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))