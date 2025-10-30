from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
import httpx
import json
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

        # Parse AI JSON and extract only the answer
        data = json.loads(res.text)
        answer = data.get("answer", "").encode("utf-8", "ignore").decode("utf-8", "ignore")

        return JSONResponse(
            content={"fullname": fullname, "reply": answer},
            ensure_ascii=False
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))