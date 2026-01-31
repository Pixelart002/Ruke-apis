import tweepy
import httpx  # Requests ki jagah async HTTP client
import time
import io
import asyncio
from urllib.parse import quote
from fastapi import APIRouter, HTTPException, status
from fastapi.concurrency import run_in_threadpool # Blocking code ko background thread me chalane ke liye
from pydantic import BaseModel, Field
from typing import Dict, Any

# --- AI CONFIGURATION ---
FLUX_IMAGE_BASE_URL = "https://flux-schnell.hello-kaiiddo.workers.dev/img"
TEXT_API_URL = "https://text.pollinations.ai"

# --- ROUTER SETUP ---
router = APIRouter(
    prefix="/api/v1/automation",
    tags=["AI Poster Automation"]
)

# --- SCHEMAS ---
class TriggerRequest(BaseModel):
    """फ्रंटएंड से प्राप्त होने वाले सभी आवश्यक डेटा के लिए स्कीमा।"""
    api_key: str = Field(..., description="Twitter/X API Key")
    api_key_secret: str = Field(..., description="Twitter/X API Key Secret")
    access_token: str = Field(..., description="Twitter/X Access Token")
    access_token_secret: str = Field(..., description="Twitter/X Access Token Secret")
    image_prompt: str = Field(..., description="Flux Image Generation Prompt")
    text_prompt: str = Field(..., description="Pollinations Text Generation Prompt")

class PostResponse(BaseModel):
    status: str
    post_id: str
    message: str
    caption_used: str

# --- CORE FUNCTIONS ---

def get_twitter_auth(keys: TriggerRequest) -> Dict[str, Any]:
    """Sync function to create Tweepy objects (Blocking but fast)."""
    auth = tweepy.OAuth1UserHandler(
        keys.api_key, keys.api_key_secret,
        keys.access_token, keys.access_token_secret
    )
    api = tweepy.API(auth) # V1.1 for Media Upload
    client = tweepy.Client( # V2 for Posting
        consumer_key=keys.api_key, consumer_secret=keys.api_key_secret,
        access_token=keys.access_token, access_token_secret=keys.access_token_secret
    )
    return {"api": api, "client": client}

# --- 1. ASYNC AI GENERATION (Fast & Non-Blocking) ---
async def generate_ai_content_async(image_prompt: str, text_prompt: str) -> tuple:
    """httpx ka upyog karke Non-blocking tareeke se content generate karta hai."""
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        # --- Image Generation ---
        encoded_image_prompt = quote(image_prompt)
        timestamp = int(time.time())
        image_url = f"{FLUX_IMAGE_BASE_URL}?prompt={encoded_image_prompt}&t={timestamp}"
        
        print(f"   [INFO] Requesting Flux image (Async)...")
        try:
            img_response = await client.get(image_url)
            img_response.raise_for_status()
            image_bytes = io.BytesIO(img_response.content)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Image generation failed: {e}")

        # --- Text Generation ---
        encoded_text_prompt = quote(text_prompt)
        text_url = f"{TEXT_API_URL}/{encoded_text_prompt}"
        
        print(f"   [INFO] Requesting Pollinations text (Async)...")
        try:
            text_response = await client.get(text_url)
            text_response.raise_for_status()
            caption = text_response.text.strip().replace('Pollinations', '').strip()
        except Exception as e:
            print(f"   [WARN] Text failed: {e}. Using fallback.")
            caption = f"AI Art: {image_prompt[:50]}..."

    return image_bytes, caption

# --- 2. TWITTER POSTING (Blocking Logic Wrapped) ---
def _post_to_twitter_sync(auth_objects: Dict[str, Any], image_bytes: io.BytesIO, text_content: str) -> Dict[str, str]:
    """
    Yeh function sync (blocking) hai kyunki Tweepy sync hai.
    Hum isse run_in_threadpool ke zariye call karenge.
    """
    api: tweepy.API = auth_objects["api"]
    client: tweepy.Client = auth_objects["client"]

    try:
        # 1. Media Upload (V1.1)
        print("   [INFO] Uploading media to X (Threaded)...")
        # Seek start of file just in case
        image_bytes.seek(0)
        media = api.media_upload(filename="ai_image.jpg", file=image_bytes)
        media_id = media.media_id_string
        print(f"   [SUCCESS] Media ID: {media_id}")

        # 2. Create Tweet (V2)
        print("   [INFO] Creating tweet (V2)...")
        response = client.create_tweet(text=text_content, media_ids=[media_id])
        return {"post_id": str(response.data['id']), "message": "Posted with Image (V2)"}

    except tweepy.TweepyException as e:
        err_msg = str(e)
        print(f"🚨 Tweepy Error: {err_msg}")
        
        # 403 Forbidden Fallback (Free Tier limitation)
        if "403" in err_msg or "453" in err_msg:
            print("   [FALLBACK] 403 Detected. Sending Text-Only Tweet...")
            try:
                client.create_tweet(text=f"🖼️ [Image Limit Reached]\n\n{text_content}")
                return {"post_id": "TEXT_ONLY", "message": "Posted Text-Only (Free Tier Limit)"}
            except Exception as sub_e:
                raise HTTPException(500, f"Fallback failed: {sub_e}")
        
        raise HTTPException(500, f"Twitter API Error: {err_msg}")

# --- 3. ENDPOINT DEFINITION ---

@router.post(
    "/trigger-post",
    response_model=PostResponse,
    status_code=status.HTTP_202_ACCEPTED
)
async def trigger_post(request_data: TriggerRequest):
    """
    Fully Async & Threaded Automation Pipeline.
    Server ko block nahi karega.
    """
    print("\n--- 🚀 NEW AUTOMATION TRIGGERED ---")

    # 1. Auth Objects create karo (Fast sync operation)
    auth_objects = get_twitter_auth(request_data)

    # 2. AI Content Generate karo (ASYNC IO - Non Blocking)
    # Httpx use karega, toh server free rahega dusri requests ke liye
    image_bytes, caption = await generate_ai_content_async(
        request_data.image_prompt, 
        request_data.text_prompt
    )

    # 3. Twitter Post karo (Blocking I/O in ThreadPool)
    # Tweepy ko main thread se hata kar worker thread mein daal diya
    post_result = await run_in_threadpool(
        _post_to_twitter_sync, 
        auth_objects, 
        image_bytes, 
        caption
    )

    print(f"--- ✅ DONE --- ID: {post_result['post_id']}")

    return {
        "status": "success",
        "post_id": post_result['post_id'],
        "message": post_result['message'],
        "caption_used": caption
    }