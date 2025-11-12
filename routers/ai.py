from fastapi import APIRouter, Depends, HTTPException, Body, Query
from fastapi.responses import JSONResponse
import httpx, json, time, urllib.parse, re
from typing import Dict, Any
from auth import utils as auth_utils

router = APIRouter(
    prefix="/ai",
    tags=["AI Core"]
)

# ============================================================
# Utility Helpers
# ============================================================

def clean_surrogates(text: str) -> str:
    """
    Removes invalid surrogate pairs and returns clean UTF-8 text.
    Ensures emojis and special characters render properly.
    """
    if not isinstance(text, str):
        text = str(text)
    return text.encode("utf-8", "surrogatepass").decode("utf-8", "ignore")


def detect_image_intent(text: str) -> bool:
    """
    Detects whether the user's message implies an image generation request.
    Triggers if text contains words like 'draw', 'generate image', 'show me', etc.
    """
    if not text:
        return False
    keywords = [
        r"\bdraw\b", r"\bimage\b", r"\bpicture\b", r"\bphoto\b",
        r"\bgenerate\b", r"\bcreate\b", r"\bshow me\b"
    ]
    return any(re.search(k, text.lower()) for k in keywords)


async def call_mistral(fullname: str, question: str) -> str:
    """Handles async call to the Mistral text endpoint."""
    encoded_q = urllib.parse.quote(question)
    mistral_url = f"https://mistral-ai-three.vercel.app/?id={fullname}&question={encoded_q}"

    async with httpx.AsyncClient() as client:
        res = await client.get(mistral_url, timeout=60)

    if res.status_code != 200:
        raise HTTPException(status_code=res.status_code, detail="Upstream error from Mistral API")

    try:
        data = res.json()
    except Exception:
        data = json.loads(res.text)

    answer_raw = data.get("answer", "")
    return clean_surrogates(answer_raw)


async def call_flux(prompt: str) -> str:
    """Handles async call to Flux Schnell image endpoint."""
    encoded_prompt = urllib.parse.quote(prompt)
    timestamp = int(time.time())
    img_url = f"https://flux-schnell.hello-kaiiddo.workers.dev/img?prompt={encoded_prompt}&t={timestamp}"

    # Optional verification of response
    async with httpx.AsyncClient() as client:
        res = await client.get(img_url, timeout=60)

    if res.status_code != 200:
        raise HTTPException(status_code=res.status_code, detail="Flux Schnell image generation failed.")

    return img_url


# ============================================================
# Individual Endpoints
# ============================================================

@router.get("/ask")
async def ask_get(
    question: str = Query(..., description="User question"),
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    """Text-based AI reply using Mistral API (GET version)."""
    try:
        fullname = current_user.get("fullname", "UnknownUser")
        answer = await call_mistral(fullname, question)
        return JSONResponse(content={"fullname": fullname, "reply": answer}, ensure_ascii=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ask")
async def ask_post(
    payload: Dict = Body(..., example={"question": "Hello, how are you?"}),
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    """Text-based AI reply using Mistral API (POST version)."""
    try:
        question = payload.get("question")
        if not question:
            raise HTTPException(status_code=400, detail="Missing 'question' field.")

        fullname = current_user.get("fullname", "UnknownUser")
        answer = await call_mistral(fullname, question)
        return JSONResponse(content={"fullname": fullname, "reply": answer}, ensure_ascii=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/image")
async def generate_image(
    payload: Dict = Body(..., example={"prompt": "A futuristic cityscape at sunset"}),
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    """Image generation using Flux Schnell API."""
    try:
        prompt = payload.get("prompt")
        if not prompt:
            raise HTTPException(status_code=400, detail="Missing 'prompt' field.")

        img_url = await call_flux(prompt)
        return JSONResponse(
            content={
                "fullname": current_user.get("fullname", "UnknownUser"),
                "prompt": prompt,
                "image_url": img_url
            },
            ensure_ascii=False
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Smart Unified Endpoint
# ============================================================

@router.post("/process")
async def ai_process(
    payload: Dict = Body(..., example={"input": "Draw a dragon flying over mountains"}),
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    """
    POST /ai/process
    Automatically decides between text reply or image generation.
    Body: {"input": "Generate an image of a sunset cityscape"} or {"input": "Explain quantum mechanics"}
    """
    try:
        user_input = payload.get("input")
        if not user_input:
            raise HTTPException(status_code=400, detail="Missing 'input' field.")

        fullname = current_user.get("fullname", "UnknownUser")

        if detect_image_intent(user_input):
            img_url = await call_flux(user_input)
            return JSONResponse(
                content={
                    "fullname": fullname,
                    "mode": "image",
                    "prompt": user_input,
                    "image_url": img_url
                },
                ensure_ascii=False
            )

        # Otherwise, process as chat
        answer = await call_mistral(fullname, user_input)
        return JSONResponse(
            content={
                "fullname": fullname,
                "mode": "chat",
                "question": user_input,
                "reply": answer
            },
            ensure_ascii=False
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))