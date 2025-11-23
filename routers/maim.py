import tweepy
import requests
import os
import time
import io
from urllib.parse import quote
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any
from starlette import status

# --- AI CONFIGURATION (AI कॉन्फ़िगरेशन) ---
FLUX_IMAGE_BASE_URL = "https://flux-schnell.hello-kaiiddo.workers.dev/img"
TEXT_API_URL = "https://text.pollinations.ai"


# --- 2. FASTAPI SCHEMAS AND ROUTER SETUP ---

# डेटा स्कीमा जो क्रेडेंशियल और प्रॉम्प्ट्स को फ़्रंटएंड से स्वीकार करेगी
class TriggerRequest(BaseModel):
    """फ्रंटएंड से प्राप्त होने वाले सभी आवश्यक डेटा के लिए स्कीमा।"""
    # Twitter Credentials (X क्रेडेंशियल)
    api_key: str = Field(..., description="Twitter/X API Key (Consumer Key)")
    api_key_secret: str = Field(..., description="Twitter/X API Key Secret (Consumer Secret)")
    access_token: str = Field(..., description="Twitter/X Access Token")
    access_token_secret: str = Field(..., description="Twitter/X Access Token Secret")

    # Content Prompts (कंटेंट प्रॉम्प्ट्स)
    image_prompt: str = Field(..., description="Flux Image Generation Prompt")
    text_prompt: str = Field(..., description="Pollinations Text Generation Prompt")


# API रिस्पॉन्स स्कीमा
class PostResponse(BaseModel):
    status: str
    post_id: str
    message: str
    caption_used: str


# APIRouter को इनिशियलाइज़ करें
router = APIRouter(
    prefix="/api/v1/automation",
    tags=["AI Poster Automation"]
)

# --- 3. CORE AUTOMATION FUNCTIONS ---

# V2: अब यह फ़ंक्शन V1.1 API (मीडिया अपलोड के लिए) और V2 Client (ट्वीट पोस्ट करने के लिए) दोनों लौटाता है।
def authenticate_twitter(keys: TriggerRequest) -> Dict[str, Any]:
    """रिक्वेस्ट बॉडी से प्राप्त क्रेडेंशियल के साथ X API को प्रमाणित करता है।"""

    auth = tweepy.OAuth1UserHandler(
        keys.api_key,
        keys.api_key_secret,
        keys.access_token,
        keys.access_token_secret
    )

    # 1. V1.1 API ऑब्जेक्ट (मीडिया अपलोड के लिए आवश्यक)
    api = tweepy.API(auth)
    api.verify_credentials()

    # 2. V2 Client ऑब्जेक्ट (ट्वीट बनाने के लिए आवश्यक)
    client = tweepy.Client(
        consumer_key=keys.api_key,
        consumer_secret=keys.api_key_secret,
        access_token=keys.access_token,
        access_token_secret=keys.access_token_secret
    )

    return {"api": api, "client": client}


def generate_ai_content(image_prompt: str, text_prompt: str) -> tuple:
    """इमेज (Flux) और टेक्स्ट (Pollinations) जेनरेट करता है।"""

    # --- Image Generation (Flux API) ---
    encoded_image_prompt = quote(image_prompt)
    timestamp = int(time.time())
    image_url = f"{FLUX_IMAGE_BASE_URL}?prompt={encoded_image_prompt}&t={timestamp}"

    print(f"   [INFO] Requesting Flux image...")
    try:
        img_response = requests.get(image_url, timeout=45)
        img_response.raise_for_status()
        image_bytes = io.BytesIO(img_response.content)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Image generation failed (Flux API): {e}")

    # --- Text Generation (Pollinations API) ---
    encoded_text_prompt = quote(text_prompt)
    text_url = f"{TEXT_API_URL}/{encoded_text_prompt}"

    print(f"   [INFO] Requesting Pollinations text...")
    try:
        text_response = requests.get(text_url, timeout=30)
        text_response.raise_for_status()
        caption = text_response.text.strip()

        # 'Pollinations' ब्रांडिंग हटा दें
        caption = caption.replace('Pollinations', '').strip()

    except Exception as e:
        print(f"   [WARN] Text generation failed: {e}. Using fallback.")
        caption = f"एक नया AI मास्टरपीस जेनरेट हुआ। प्रॉम्प्ट: {image_prompt[:80]}..."

    return image_bytes, caption


# V2 Fix: अब यह API और Client दोनों ऑब्जेक्ट स्वीकार करता है
def post_to_twitter_endpoint(auth_objects: Dict[str, Any], image_bytes: io.BytesIO, text_content: str) -> Dict[str, str]:
    """X पर पोस्ट करने की दो-चरणीय प्रक्रिया संभालता है, 403 होने पर टेक्स्ट-ओनली फॉलबैक करता है।"""

    api: tweepy.API = auth_objects["api"]
    client: tweepy.Client = auth_objects["client"]
    media_id_string = None

    try:
        # 1. मीडिया अपलोड (V1.1 का उपयोग करके)
        print("   [INFO] Uploading media to X server (V1.1)...")

        try:
            # Tweepy V1.1 API का उपयोग मीडिया अपलोड के लिए करें
            media = api.media_upload(filename="ai_image.jpg", file=image_bytes)
            media_id_string = media.media_id_string
            print("   [SUCCESS] Media uploaded. ID:", media_id_string)

            # 2. ट्वीट पोस्ट करें (V2 Client का उपयोग करके)
            print("   [INFO] Creating tweet with image (V2)...")
            response = client.create_tweet(
                text=text_content,
                media_ids=[media_id_string]
            )
            return {"post_id": response.data['id'], "message": "Post successful with image (V2)."}

        except tweepy.TweepyException as e:
            error_message = str(e)
            print(f"🚨🚨 CRITICAL TWEEPY ERROR DETAIL: {error_message}")

            # 🚨 403 Forbidden (453) Error को पहचानें
            if "403 Forbidden" in error_message or "453" in error_message:
                print("   [FALLBACK] 403/453 error detected. Falling back to text-only post (V2)...")

                # --- V2 Text-Only फॉलबैक ---
                # केवल टेक्स्ट के साथ पोस्ट करें (यह फ्री टियर पर काम करना चाहिए)
                client.create_tweet(text=f"🖼️ [Image not posted due to Free Tier restriction].\n\n{text_content}")

                # V2 Free Tier पर पोस्टिंग सफल हुई, लेकिन इमेज नहीं है।
                return {"post_id": "TEXT_ONLY_FALLBACK", "message": "Post successful (Text-Only) due to API access limits. Please upgrade your X API access level to enable image posting."}

            else:
                # यदि 403 के अलावा कोई अन्य गंभीर त्रुटि है
                raise HTTPException(status_code=500, detail=f"X API Error during post: {error_message}")

    except Exception as e:
        # अन्य सभी अनपेक्षित त्रुटियाँ
        raise HTTPException(status_code=500, detail=f"Unexpected error during posting: {e}")


# --- 4. ROUTER ENDPOINT DEFINITION ---

@router.post(
    "/trigger-post",
    response_model=PostResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="फ्रंटएंड से क्रेडेंशियल्स के साथ AI पोस्ट को ट्रिगर करता है।"
)
async def trigger_post(request_data: TriggerRequest):
    """
    फ्रंटएंड से प्राप्त डेटा का उपयोग करके संपूर्ण AI कंटेंट पाइपलाइन को निष्पादित करता है।
    """
    print("\n--- NEW AUTOMATION TRIGGERED ---")

    try:
        # 1. Authenticate with X using body data (Returns API & Client)
        auth_objects = authenticate_twitter(request_data)

        # 2. Generate content using body data
        image_bytes, caption = generate_ai_content(request_data.image_prompt, request_data.text_prompt)

        # 3. Post to X (uses V1.1 for media, V2 for post, includes the 403 fallback)
        post_result = post_to_twitter_endpoint(auth_objects, image_bytes, caption)

        print(f"--- STATUS --- Post ID: {post_result['post_id']} | Message: {post_result['message']}")

        return {
            "status": "success",
            "post_id": post_result['post_id'],
            "message": post_result['message'],
            "caption_used": caption
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"   [CRITICAL] Unhandled Error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")
