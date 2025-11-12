# routers/ai.py
import os
import time
import json
import urllib.parse
from pathlib import Path
from typing import Dict

import httpx
import google.generativeai as genai
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from auth import utils as auth_utils  # your dependency

# === ROUTER ===
router = APIRouter(
    prefix="/ai",
    tags=["AI Core"]
)

# === CONFIG PATHS ===
BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"

def load_text(path: Path, fallback: str = "") -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return fallback

def load_json(path: Path, fallback=None) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return fallback or {}

# Ensure config dir exists (no-op if present)
try:
    CONFIG_DIR.mkdir(exist_ok=True)
except Exception:
    pass

SYSTEM_PROMPT = load_text(
    CONFIG_DIR / "system_prompt.txt",
    "You are Anya — a professional, emotionally intelligent AI assistant."
)

MODELS = load_json(
    CONFIG_DIR / "models.json",
    {
        "gemini_model": "gemini-2.5-flash-lite",
        "mistral_url": "https://mistral-ai-three.vercel.app/?id={id}&question={q}",
        "flux_url": "https://flux-schnell.hello-kaiiddo.workers.dev/img?prompt={p}&t={t}"
    }
)

# === GEMINI CONFIG ===
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# === REQUEST MODEL ===
class AIPrompt(BaseModel):
    prompt: str
    mode: str = "gemini"   # "gemini", "mistral", or "image"

# === ROUTES ===
@router.post("/ask")
async def ask_gemini(
    request: AIPrompt,
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    if not request.prompt or not request.prompt.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Directive cannot be empty."
        )

    user_id = str(current_user.get("id", "guest"))
    mode = (request.mode or "gemini").lower().strip()
    user_prompt = request.prompt.strip()
    full_prompt = f"{SYSTEM_PROMPT}\n\nUser: {user_prompt}"

    try:
        # -------------------------
        # GEMINI (text)
        # -------------------------
        if mode == "gemini":
            if not GEMINI_API_KEY:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Gemini API key not configured."
                )
            model = genai.GenerativeModel(MODELS.get("gemini_model", "gemini-2.5-flash-lite"))
            response = model.generate_content(full_prompt)
            return {
                "engine": "Gemini",
                "type": "text",
                "response": response.text.strip()
            }

        # -------------------------
        # MISTRAL (text)
        # -------------------------
        elif mode == "mistral":
            # URL-encode the full prompt for the query param
            q = urllib.parse.quote_plus(full_prompt)
            mistral_url = MODELS["mistral_url"].format(id=user_id, q=q)
            async with httpx.AsyncClient(timeout=30) as client:
                res = await client.get(mistral_url)
            if res.status_code == 200:
                return {
                    "engine": "Mistral",
                    "type": "text",
                    "response": res.text.strip()
                }
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Mistral API failed to respond."
            )

        # -------------------------
        # FLUX SCHNELL (image) with auto-professionalization via Mistral
        # -------------------------
        elif mode == "image":
            # 1) Ask Mistral to professionalize the user prompt
            enhance_instruction = f"Professionalize and expand this image generation prompt for a photo/illustration: {user_prompt}"
            enhance_q = urllib.parse.quote_plus(f"{SYSTEM_PROMPT}\n\nInstruction: {enhance_instruction}")
            mistral_url = MODELS["mistral_url"].format(id=user_id, q=enhance_q)

            async with httpx.AsyncClient(timeout=30) as client:
                enhance_res = await client.get(mistral_url)
            if enhance_res.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Failed to enhance image prompt via Mistral."
                )
            enhanced_prompt = enhance_res.text.strip()

            # 2) Call Flux Schnell with the enhanced prompt
            encoded_prompt = urllib.parse.quote(enhanced_prompt)
            timestamp = str(int(time.time()))
            img_url = MODELS["flux_url"].format(p=encoded_prompt, t=timestamp)

            async with httpx.AsyncClient(timeout=60) as client:
                img_res = await client.get(img_url)
            if img_res.status_code == 200:
                return {
                    "engine": "Flux Schnell",
                    "type": "image",
                    "image_url": img_url,
                    "original_prompt": user_prompt,
                    "enhanced_prompt": enhanced_prompt
                }

            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Flux Schnell image generation failed."
            )

        # -------------------------
        # INVALID MODE
        # -------------------------
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid mode. Choose 'gemini', 'mistral', or 'image'."
            )

    except HTTPException:
        # Re-raise HTTPExceptions so FastAPI handles them as-is
        raise
    except Exception as e:
        # Log server-side error and return generic service unavailable message
        print(f"[AI Router] Internal Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI Core encountered an internal error."
        )