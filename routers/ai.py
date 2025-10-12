import os
import httpx
import json
import uuid
from urllib.parse import quote_plus
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Form, UploadFile, File, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List

from auth import utils as auth_utils
from database import db
from bson import ObjectId

router = APIRouter(prefix="/ai", tags=["AI Core"])

# Sandboxed Environment ke liye static folder mount karein
os.makedirs("static/sandboxed", exist_ok=True)
router.mount("/static", StaticFiles(directory="static"), name="static")


# --- RAG Knowledge Base: AI Directory of Tools ---
TOOL_REGISTRY = {
    "image_generation_midjourney": {
        "name": "MidJourney", "description": "High-quality, artistic image generation.",
        "base_url": "https://midapi.vasarai.net/api/v1/images/generate-image", "method": "POST",
        "headers": {"Authorization": "Bearer vasarai"}, "params": {"message": "{prompt}"},
        "response_mapping": {"type": "image_url", "path": "cdn_url"}
    },
    "code_generation": {
        "name": "Code Generator", "description": "Writes code, creates full websites with multiple files.",
        "base_url": "https://text.hello-kaiiddo.workers.dev/generate", "method": "GET",
        "params": {"q": "{prompt}", "model": "openai", "system": "You are an expert web developer. If asked for a website, provide a JSON object with filenames as keys (e.g., 'index.html', 'style.css') and code as string values. For single code snippets, use markdown."},
        "response_mapping": {"type": "code", "path": "response"}
    },
    "creative_writing_mistral": {
        "name": "Mistral AI", "description": "Creative text, conversations, and detailed explanations.",
        "base_url": "https://mistral-ai-three.vercel.app/", "method": "GET",
        "params": {"id": "{user_id}", "question": "{prompt}"},
        "response_is_plain_text": True, "response_mapping": {"type": "text"}
    }
}

# --- Rich UI Templates ---
HTML_TEMPLATES = {
    "image_preview_card": """<div class="glass-panel p-4 my-4 rounded-lg"><p class="text-sm text-text-secondary mb-2">Image Preview:</p><img src="{url}" class="rounded-md max-w-full"><div class="mt-4"><a href="{url}" download="{filename}" class="tactical-btn py-2 px-4 rounded-md text-sm inline-flex items-center"><svg class="h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V3" /></svg>Download</a></div></div>""",
    "info_card": """<div class="glass-panel border-l-4 border-yellow-400 p-4 my-4 rounded-lg"><p class="text-yellow-200 text-sm font-bold">Important Information</p><p class="text-text-primary text-sm mt-2">{message}</p></div>"""
}

# --- Helper Functions ---
def get_chat_history(chat_id: str):
    if not chat_id: return []
    return list(db.chat_histories.find({"chat_id": chat_id}).sort("timestamp", -1).limit(4))

def save_to_history(chat_id: str, user_prompt: str, yuku_response: Dict):
    if not chat_id: return
    db.chat_histories.insert_one({"chat_id": chat_id, "role": "user", "content": user_prompt, "timestamp": datetime.now(timezone.utc)})
    db.chat_histories.insert_one({"chat_id": chat_id, "role": "assistant", "content": yuku_response, "timestamp": datetime.now(timezone.utc)})

async def get_router_ai_decision(system_prompt: str) -> Dict:
    router_url = f"https://mistral-ai-three.vercel.app/?id=yuku-router&question={quote_plus(system_prompt)}"
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(router_url, timeout=45.0)
            res.raise_for_status()
            decision_str = res.text.strip().replace("```json", "").replace("```", "")
            return json.loads(decision_str)
        except Exception: return {}

async def choose_tool_and_generate_chips(user_prompt: str, history: List[Dict]) -> Dict:
    # ... (Logic remains the same as previous version)
    return await get_router_ai_decision(f"You are YUKU's brain... LATEST User Prompt: '{user_prompt}'")


# --- API Endpoints ---
class SandboxRequest(BaseModel):
    files: Dict[str, str]

@router.post("/sandbox/host")
async def host_sandboxed_code(req: SandboxRequest, current_user: Dict = Depends(auth_utils.get_current_user)):
    slug = str(uuid.uuid4())
    project_path = os.path.join("static/sandboxed", slug)
    os.makedirs(project_path, exist_ok=True)
    if "index.html" not in req.files: raise HTTPException(status_code=400, detail="index.html is required.")
    for filename, content in req.files.items():
        if ".." in filename or filename.startswith("/"): raise HTTPException(status_code=400, detail="Invalid filename.")
        with open(os.path.join(project_path, filename), "w", encoding="utf-8") as f: f.write(content)
    return {"status": "ok", "preview_url": f"/ai/static/sandboxed/{slug}/index.html"}

@router.get("/tools")
async def get_tools_list():
    return TOOL_REGISTRY

@router.post("/ask")
async def ask_yuku_mcp(prompt: str = Form(...), chat_id: str = Form(...), tool_override: Optional[str] = Form(None), current_user: Dict = Depends(auth_utils.get_current_user)):
    history = get_chat_history(chat_id)
    user_id = str(current_user["_id"])
    
    if tool_override in TOOL_REGISTRY:
        decision = {"tool_name": tool_override, "prompt_for_tool": prompt}
    else:
        decision = await choose_tool_and_generate_chips(prompt, history)

    chosen_tool = decision.get("tool_name", "creative_writing_mistral")
    prompt_for_tool = decision.get("prompt_for_tool", prompt)
    chips = decision.get("chips", [f"Explain '{prompt.split()[-1]}' more", "Generate an image for this"])
    
    tool = TOOL_REGISTRY[chosen_tool]
    yuku_response = {}
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            # ... (API calling logic remains the same) ...
            placeholders = {"prompt": quote_plus(prompt_for_tool), "user_id": user_id}
            formatted_params = {k: v.format(**placeholders) for k, v in tool.get("params", {}).items()}
            api_response = await client.get(tool["base_url"], params=formatted_params)
            api_response.raise_for_status()

            if tool.get("response_is_image_url"):
                img_url = str(api_response.url)
                yuku_response = {"type": "html_template", "content": HTML_TEMPLATES["image_preview_card"].format(url=img_url, filename="generated_image.png")}
            elif tool.get("response_is_plain_text"):
                yuku_response = {"type": "text", "content": api_response.text}
            else:
                data = api_response.json()
                content = data.get(tool["response_mapping"]["path"], "Error processing response.")
                if content.strip().startswith("{") and '"index.html"' in content:
                    yuku_response = {"type": "code_project", "content": json.loads(content)}
                else:
                    yuku_response = {"type": "text", "content": content}

        except Exception as e:
            yuku_response = {"type": "error", "content": str(e)}
    
    yuku_response["source"] = tool["name"]
    yuku_response["chips"] = chips
    
    save_to_history(chat_id, prompt, yuku_response)
    return {"yuku_response": yuku_response}
