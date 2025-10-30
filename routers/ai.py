from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import JSONResponse
import httpx, json
from typing import Dict
from auth import utils as auth_utils

router = APIRouter(
    prefix="/ai",
    tags=["AI Core"]
)

# ------------------ Utility ------------------ #
def clean_surrogates(text: str) -> str:
    """
    Removes invalid surrogate pairs and returns clean UTF-8 text.
    Ensures emojis and special characters render properly.
    """
    if not isinstance(text, str):
        text = str(text)
    return text.encode("utf-8", "surrogatepass").decode("utf-8", "ignore")

# ------------------ GET Endpoint ------------------ #
@router.get("/ask")
async def ask_get(question: str, current_user: Dict = Depends(auth_utils.get_current_user)):
    """
    GET /ai/ask?question=Hello
    Uses user's fullname as the AI session ID.
    """
    try:
        fullname = current_user.get("fullname", "UnknownUser")

        mistral_url = f"https://mistral-ai-three.vercel.app/?id={fullname}&question={question}"

        async with httpx.AsyncClient() as client:
            res = await client.get(mistral_url, timeout=60)

        data = json.loads(res.text)
        answer_raw = data.get("answer", "")
        answer_clean = clean_surrogates(answer_raw)

        return JSONResponse(
            content={"fullname": fullname, "reply": answer_clean},
            ensure_ascii=False
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ------------------ POST Endpoint ------------------ #
@router.post("/ask")
async def ask_post(
    payload: Dict = Body(...),
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    """
    POST /ai/ask
    Body: {"question": "Your text here"}
    """
    try:
        question = payload.get("question")
        if not question:
            raise HTTPException(status_code=400, detail="Missing 'question' field.")

        fullname = current_user.get("fullname", "UnknownUser")

        mistral_url = f"https://mistral-ai-three.vercel.app/?id={fullname}&question={question}"

        async with httpx.AsyncClient() as client:
            res = await client.get(mistral_url, timeout=60)

        data = json.loads(res.text)
        answer_raw = data.get("answer", "")
        answer_clean = clean_surrogates(answer_raw)

        return JSONResponse(
            content={"fullname": fullname, "reply": answer_clean},
            ensure_ascii=False
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))