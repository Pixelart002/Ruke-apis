# routers/ai.py
import os
import time
import json
import urllib.parse
import logging
from pathlib import Path
from typing import Dict
from enum import Enum

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

# === LOGGER ===
# Use a proper logger instead of print() for errors
logger = logging.getLogger(__name__)

# === CONFIG PATHS ===
# [FIX] Changed BASE_DIR to parent.parent
# This assumes your directory structure is:
# project_root/
#  ├── routers/
#  │   └── ai.py
#  └── config/
#      ├── system_prompt.txt
#      └── models.json
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"

def load_text(path: Path, fallback: str = "") -> str:
    """Safely load a text file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception as e:
        logger.warning(f"Failed to load text file {path}: {e}")
        return fallback

def load_json(path: Path, fallback=None) -> dict:
    """Safely load a JSON file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load JSON file {path}: {e}")
        return fallback or {}

# Ensure config dir exists (no-op if present)
try:
    CONFIG_DIR.mkdir(exist_ok=True)
except Exception as e:
    logger.error(f"Could not create config directory at {CONFIG_DIR}: {e}")

SYSTEM_PROMPT = load_text(
    CONFIG_DIR / "system_prompt.txt",
    "You are Anya — a professional, emotionally intelligent AI assistant."
)

MODELS = load_json(
    CONFIG_DIR / "models.json",
    {
        "gemini_model": "gemini-1.5-flash", # Updated to a common modern model
        "mistral_url": "https://mistral-ai-three.vercel.app/?id={id}&question={q}",
        "flux_url": "https://flux-schnell.hello-kaiiddo.workers.dev/img?prompt={p}&t={t}"
    }
)

# === GEMINI CONFIG ===
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    logger.warning("GEMINI_API_KEY environment variable not set.")

# === REQUEST MODELS ===
# [ENHANCE] Use Enum for mode for validation and clarity
class AIEngine(str, Enum):
    GEMINI = "gemini"
    MISTRAL = "mistral"
    IMAGE = "image"

class AIPrompt(BaseModel):
    prompt: str
    mode: AIEngine = AIEngine.GEMINI  # "gemini", "mistral", or "image"

# === ROUTES ===
@router.post("/ask")
async def ask_ai(
    request: AIPrompt,
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    """
    Master AI endpoint to route requests to Gemini, Mistral, or Flux (Image Gen).
    """
    if not request.prompt or not request.prompt.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Directive cannot be empty."
        )

    user_id = str(current_user.get("id", "guest"))
    mode = request.mode
    user_prompt = request.prompt.strip()
    full_prompt = f"{SYSTEM_PROMPT}\n\nUser: {user_prompt}"

    try:
        # -------------------------
        # GEMINI (text)
        # -------------------------
        if mode == AIEngine.GEMINI:
            if not GEMINI_API_KEY:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Gemini API key not configured."
                )
            model = genai.GenerativeModel(MODELS.get("gemini_model", "gemini-1.5-flash"))
            response = await model.generate_content_async(full_prompt) # Use async
            return {
                "engine": "Gemini",
                "type": "text",
                "response": response.text.strip()
            }

        # -------------------------
        # MISTRAL (text)
        # -------------------------
        elif mode == AIEngine.MISTRAL:
            # [FIX] Use urllib.parse.quote for URL query parameters, not quote_plus
            q = urllib.parse.quote(full_prompt)
            u_id = urllib.parse.quote(user_id)
            mistral_url = MODELS["mistral_url"].format(id=u_id, q=q)
            
            async with httpx.AsyncClient(timeout=30) as client:
                try:
                    res = await client.get(mistral_url)
                    res.raise_for_status()  # Check for 4xx/5xx errors
                except httpx.HTTPStatusError as http_err:
                    logger.warning(f"Mistral API request failed: {http_err}")
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=f"Mistral API failed: {http_err.response.status_code}"
                    )
                except httpx.RequestError as req_err:
                    logger.warning(f"Mistral API connection error: {req_err}")
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Mistral API connection failed."
                    )
                
                return {
                    "engine": "Mistral",
                    "type": "text",
                    "response": res.text.strip()
                }

        # -------------------------
        # FLUX SCHNELL (image)
        # -------------------------
        elif mode == AIEngine.IMAGE:
            # 1) Ask Mistral to professionalize the user prompt
            enhance_instruction = f"Professionalize and expand this image generation prompt for a photo/illustration: {user_prompt}"
            enhance_q = urllib.parse.quote(f"{SYSTEM_PROMPT}\n\nInstruction: {enhance_instruction}")
            u_id = urllib.parse.quote(user_id)
            mistral_url = MODELS["mistral_url"].format(id=u_id, q=enhance_q)

            enhanced_prompt = ""
            
            # [ENHANCE] Use a single client for both requests
            async with httpx.AsyncClient(timeout=90.0) as client:
                # --- Mistral Call ---
                try:
                    enhance_res = await client.get(mistral_url, timeout=30.0)
                    enhance_res.raise_for_status()
                except httpx.HTTPStatusError as http_err:
                    logger.warning(f"Image prompt enhance (Mistral) failed: {http_err}")
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Failed to enhance image prompt via Mistral."
                    )
                except httpx.RequestError as req_err:
                    logger.warning(f"Image prompt enhance (Mistral) connection error: {req_err}")
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Image prompt enhancement service connection failed."
                    )
                
                enhanced_prompt = enhance_res.text.strip()

                # 2) Call Flux Schnell with the enhanced prompt
                encoded_prompt = urllib.parse.quote(enhanced_prompt)
                timestamp = str(int(time.time()))
                img_url = MODELS["flux_url"].format(p=encoded_prompt, t=timestamp)

                # --- Flux Call ---
                try:
                    img_res = await client.get(img_url, timeout=60.0)
                    img_res.raise_for_status()
                except httpx.HTTPStatusError as http_err:
                    logger.warning(f"Flux Schnell image gen failed: {http_err}")
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Image generation service failed."
                    )
                except httpx.RequestError as req_err:
                    logger.warning(f"Flux Schnell connection error: {req_err}")
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Image generation service connection failed."
                    )

                # Return the URL that *would* be called, as per original script
                return {
                    "engine": "Flux Schnell",
                    "type": "image",
                    "image_url": img_url,
                    "original_prompt": user_prompt,
                    "enhanced_prompt": enhanced_prompt
                }

        # -------------------------
        # INVALID MODE
        # -------------------------
        else:
            # This case should be unreachable due to Pydantic/Enum validation
            # but is kept for exhaustive checking.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid mode."
            )

    except HTTPException:
        # Re-raise HTTPExceptions so FastAPI handles them
        raise
    except Exception as e:
        # [FIX] Use logger.error for better traceability
        logger.error(f"[AI Router] Internal Error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI Core encountered an internal error."
        )