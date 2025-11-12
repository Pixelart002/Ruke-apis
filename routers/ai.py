import os, time, json, urllib.parse, httpx
from pathlib import Path
import google.generativeai as genai
from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel
from auth import utils as auth_utils
from typing import Dict

# === CORE SETUP ===
app = FastAPI(title="Anya AI Core", version="5.0")

BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
CONFIG_DIR.mkdir(exist_ok=True)

# === UTILITIES ===
def load_text(path, fallback=""):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except:
        return fallback

def load_json(path, fallback=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return fallback or {}

# === CONFIG ===
SYSTEM_PROMPT = load_text(
    CONFIG_DIR / "system_prompt.txt",
    "You are Anya — a brilliant, emotionally intelligent AI system. Respond professionally and adaptively."
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
    mode: str = "gemini"  # "gemini", "mistral", or "image"

# === MAIN ENDPOINT ===
@app.post("/ai/ask")
async def anya_ai_core(
    request: AIPrompt,
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    if not request.prompt or not request.prompt.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Directive cannot be empty."
        )

    try:
        user_id = str(current_user.get("id", "guest"))
        mode = request.mode.lower().strip()
        user_prompt = request.prompt.strip()
        full_prompt = f"{SYSTEM_PROMPT}\n\nUser: {user_prompt}"

        # === GEMINI ===
        if mode == "gemini":
            model = genai.GenerativeModel(MODELS["gemini_model"])
            response = model.generate_content(full_prompt)
            return {
                "engine": "Gemini",
                "type": "text",
                "response": response.text.strip()
            }

        # === MISTRAL ===
        elif mode == "mistral":
            q = (
                full_prompt.replace(" ", "+")
                .replace("?", "%3F")
                .replace("&", "%26")
            )
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

        # === FLUX (AUTO-PROFESSIONALIZED IMAGE GEN) ===
        elif mode == "image":
            # Step 1: Ask Mistral to professionalize the user prompt
            enhance_q = f"Make this image prompt professional and detailed: {user_prompt}"
            q = enhance_q.replace(" ", "+").replace("?", "%3F").replace("&", "%26")
            mistral_url = MODELS["mistral_url"].format(id=user_id, q=q)
            async with httpx.AsyncClient(timeout=30) as client:
                enhance_res = await client.get(mistral_url)
            if enhance_res.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Failed to enhance image prompt via Mistral."
                )
            enhanced_prompt = enhance_res.text.strip()

            # Step 2: Generate image via Flux Schnell
            encoded_prompt = urllib.parse.quote(enhanced_prompt)
            timestamp = str(int(time.time()))
            img_url = MODELS["flux_url"].format(p=encoded_prompt, t=timestamp)

            async with httpx.AsyncClient(timeout=30) as client:
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

        # === INVALID MODE ===
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid mode. Choose 'gemini', 'mistral', or 'image'."
            )

    except Exception as e:
        print(f"Anya AI Core Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI Core encountered an internal error."
        )