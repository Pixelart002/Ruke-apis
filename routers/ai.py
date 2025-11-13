import os
import time
import json
import urllib.parse
import logging
from pathlib import Path
from typing import Dict
from enum import Enum
from datetime import datetime, timezone

import httpx
import google.generativeai as genai
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from auth import utils as auth_utils  # aapki dependency
try:
    from database import db
except ImportError:
    db = None
    logger.error("database.py file nahi mili. Chat history save nahi hogi.")

# === ROUTER ===
router = APIRouter(
    prefix="/ai",
    tags=["AI Core"]
)

# === LOGGER ===
logger = logging.getLogger(__name__)

# === CONFIG PATHS ===
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"

# === DB COLLECTION ===
try:
    if db is not None:
        chat_collection = db["chat_history"]
    else:
        chat_collection = None
except Exception as e:
    logger.error(f"Chat history collection ('chat_history') nahi mil saki: {e}")
    chat_collection = None

# ... (load_text aur load_json functions same hain) ...
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

# Directory creation logic (aapka code pehle se sahi hai)
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
        # [FIX] Model ka naam "gemini-1.5-flash-latest" kar diya gaya hai
        "gemini_model": "gemini-1.5-flash-latest",
        "mistral_url": "https://mistral-ai-three.vercel.app/?id={id}&question={q}",
        "flux_url": "https://flux-schnell.hello-kaiiddo.workers.dev/img?prompt={p}&t={t}",
        "midjourney_url": "https://midapi.vasarai.net/api/v1/images/generate-image?message={p}",
        "midjourney_token": "Bearer vasarai"
    }
)

# === GEMINI CONFIG ===
# [SECURITY] API Key ko Environment Variable se hi load karna sahi hai
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") 
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    logger.warning("GEMINI_API_KEY environment variable not set.")

# === REQUEST MODELS ===
class AIEngine(str, Enum):
    GEMINI = "gemini"
    MISTRAL = "mistral"
    IMAGE = "image" # Yeh Flux hai
    MIDJOURNEY = "midjourney" # Yeh Vasarai hai

class AIPrompt(BaseModel):
    prompt: str
    mode: AIEngine = AIEngine.GEMINI


# === MAIN ROUTE ===
@router.post("/ask")
async def ask_ai(
    request: AIPrompt,
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    """
    Master AI endpoint to route requests to Gemini, Mistral, Flux, or Midjourney.
    """
    if not request.prompt or not request.prompt.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Directive cannot be empty."
        )

    user_id = current_user.get("_id")
    user_fullname = str(current_user.get("fullname", "User"))
    
    mode = request.mode
    user_prompt = request.prompt.strip()
    
    full_prompt = f"{SYSTEM_PROMPT}\n\n{user_fullname}: {user_prompt}"
    
    response_data = {}

    try:
        # -------------------------
        # GEMINI (Text)
        # -------------------------
        if mode == AIEngine.GEMINI:
            if not GEMINI_API_KEY:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Gemini API key not configured."
                )
            
            # [FIX] Model name config se lein (gemini-1.5-flash-latest)
            model_name = MODELS.get("gemini_model", "gemini-1.5-flash-latest")
            model = genai.GenerativeModel(model_name)
            
            response = await model.generate_content_async(full_prompt)
            
            response_data = {
                "engine": "Gemini",
                "type": "text",
                "response": response.text.strip()
            }

        # -------------------------
        # MISTRAL (Text)
        # -------------------------
        elif mode == AIEngine.MISTRAL:
            q = urllib.parse.quote(full_prompt)
            u_id = urllib.parse.quote(str(user_id))
            mistral_url = MODELS["mistral_url"].format(id=u_id, q=q)

            async with httpx.AsyncClient(timeout=30) as client:
                try:
                    res = await client.get(mistral_url)
                    res.raise_for_status()
                except httpx.HTTPStatusError as http_err:
                    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Mistral API failed: {http_err.response.status_code}")
                except httpx.RequestError as req_err:
                    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Mistral API connection failed.")

                # Clean JSON logic (Aapka code pehle se sahi hai)
                try:
                    data = json.loads(res.text)
                    cleaned_response = data.get("answer", "").strip() or res.text.strip()
                except json.JSONDecodeError:
                    cleaned_response = res.text.strip()

                response_data = {
                    "engine": "Mistral",
                    "type": "text",
                    "response": cleaned_response
                }

        # -------------------------
        # FLUX SCHNELL (Image)
        # -------------------------
        elif mode == AIEngine.IMAGE:
            enhance_instruction = (
                f"Professionalize and expand this image generation prompt for a high-quality, realistic render: {user_prompt}"
            )
            enhance_q = urllib.parse.quote(
                f"{SYSTEM_PROMPT}\n\n{user_fullname}: {enhance_instruction}"
            )
            u_id = urllib.parse.quote(str(user_id))
            mistral_url = MODELS["mistral_url"].format(id=u_id, q=enhance_q)

            enhanced_prompt = ""

            async with httpx.AsyncClient(timeout=90.0) as client:
                # --- Mistral Call (for enhancing) ---
                try:
                    enhance_res = await client.get(mistral_url, timeout=30.0)
                    enhance_res.raise_for_status()
                    try:
                        data = json.loads(enhance_res.text)
                        enhanced_prompt = data.get("answer", "").strip() or enhance_res.text.strip()
                    except json.JSONDecodeError:
                        enhanced_prompt = enhance_res.text.strip()
                except Exception as e:
                    logger.warning(f"Flux enhance (Mistral) failed: {e}. Using original prompt.")
                    enhanced_prompt = user_prompt # Fallback
                
                # --- Flux Schnell Call ---
                encoded_prompt = urllib.parse.quote(enhanced_prompt)
                timestamp = str(int(time.time()))
                img_url = MODELS["flux_url"].format(p=encoded_prompt, t=timestamp)

                try:
                    img_res = await client.get(img_url, timeout=60.0)
                    img_res.raise_for_status()
                except httpx.HTTPStatusError as http_err:
                    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Flux image generation failed.")
                except httpx.RequestError as req_err:
                    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Flux image service connection failed.")

                response_data = {
                    "engine": "Flux Schnell",
                    "type": "image",
                    "image_url": img_url,
                    "original_prompt": user_prompt,
                    "enhanced_prompt": enhanced_prompt
                }
        
        # -------------------------
        # VASARAI (Midjourney)
        # -------------------------
        elif mode == AIEngine.MIDJOURNEY:
            # [NEW] Midjourney ke liye prompt enhancement
            enhance_instruction = (
                f"Professionalize and expand this image generation prompt for a high-quality, artistic render (Midjourney style): {user_prompt}"
            )
            enhance_q = urllib.parse.quote(
                f"{SYSTEM_PROMPT}\n\n{user_fullname}: {enhance_instruction}"
            )
            u_id = urllib.parse.quote(str(user_id))
            mistral_url = MODELS["mistral_url"].format(id=u_id, q=enhance_q)

            enhanced_prompt = ""
            
            async with httpx.AsyncClient(timeout=90.0) as client:
                # --- Mistral Call (for enhancing) ---
                try:
                    enhance_res = await client.get(mistral_url, timeout=30.0)
                    enhance_res.raise_for_status()
                    try:
                        data = json.loads(enhance_res.text)
                        enhanced_prompt = data.get("answer", "").strip() or enhance_res.text.strip()
                    except json.JSONDecodeError:
                        enhanced_prompt = enhance_res.text.strip()
                except Exception as e:
                    logger.warning(f"Midjourney enhance (Mistral) failed: {e}. Using original prompt.")
                    enhanced_prompt = user_prompt # Fallback

                # --- Vasarai (Midjourney) Call ---
                # [NEW] Enhanced prompt ka istemaal
                encoded_prompt = urllib.parse.quote(enhanced_prompt)
                mj_url = MODELS["midjourney_url"].format(p=encoded_prompt)
                mj_token = MODELS.get("midjourney_token", "Bearer vasarai")

                try:
                    res = await client.post(
                        mj_url,
                        headers={"Authorization": mj_token},
                        timeout=60.0 # Timeout yahan add karein
                    )
                    res.raise_for_status()
                    data = res.json()
                    cdn_url = data.get("cdn_url")

                    if not cdn_url:
                        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Midjourney API failed to return image URL.")

                    response_data = {
                        "engine": "Midjourney (Vasarai)",
                        "type": "image",
                        "image_url": cdn_url,
                        "original_prompt": user_prompt,
                        "enhanced_prompt": enhanced_prompt # Ab enhanced prompt return hoga
                    }
                except httpx.HTTPStatusError as http_err:
                    logger.error(f"Midjourney API request failed: {http_err}")
                    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Midjourney API failed.")
                except httpx.RequestError as req_err:
                    logger.error(f"Midjourney API connection error: {req_err}")
                    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Midjourney API connection failed.")
                except Exception as e:
                    logger.error(f"Midjourney response error: {e}")
                    raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Midjourney response parsing failed.")

        # -------------------------
        # INVALID MODE
        # -------------------------
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid mode. Choose 'gemini', 'mistral', 'image', or 'midjourney'."
            )

        # [Database Save Logic] (Aapka code pehle se sahi hai)
        if chat_collection is not None:
            try:
                chat_log = {
                    "user_id": user_id,
                    "prompt": user_prompt,
                    "mode": mode.value,
                    "engine": response_data.get("engine"),
                    "response_text": response_data.get("response"),
                    "image_url": response_data.get("image_url"),
                    "enhanced_prompt": response_data.get("enhanced_prompt"),
                    "created_at": datetime.now(timezone.utc)
                }
                chat_collection.insert_one(chat_log)
            except Exception as e:
                logger.error(f"Chat log ko DB mein save karne mein fail: {e}")

        return response_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[AI Router] Internal Error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI Core encountered an internal error."
        )