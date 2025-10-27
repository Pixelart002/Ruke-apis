import os
import httpx
import json
import uuid
from urllib.parse import quote_plus
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Form, UploadFile, File
from pydantic import BaseModel
from typing import Dict, Any, Optional, List

from auth import utils as auth_utils
from database import db
from bson import ObjectId

router = APIRouter(prefix="/ai", tags=["AI Core"])

# --- RAG Knowledge Base & System Prompts (Tool Registry unchanged) ---
TOOL_REGISTRY = {
    "image_generation_midjourney": {
        "name": "MidJourney", "description": "High-quality, artistic images.",
        "base_url": "https://midapi.vasarai.net/api/v1/images/generate-image", "method": "POST",
        "headers": {"Authorization": "Bearer vasarai"}, "params": {"message": "{prompt}"},
        "response_mapping": {"type": "image_url", "path": "cdn_url"}
    },
    "image_generation_flux": {
        "name": "Flux-Schnell", "description": "Very fast image generation.",
        "base_url": "https://flux-schnell.hello-kaiiddo.workers.dev/img", "method": "GET",
        "params": {"prompt": "{prompt}"}, "response_is_image_url": True
    },
    "code_generation": {
        "name": "Code Generator", "description": "Writes code, creates full websites.",
        "base_url": "https://text.hello-kaiiddo.workers.dev/generate", "method": "GET",
        "params": {"q": "{prompt}", "model": "openai", "system": "You are a YUKU AI code generation module. If asked for a website, provide a JSON object with filenames as keys (e.g., 'index.html', 'style.css') and the complete code as string values. For single code snippets, use markdown with language identifiers."},
        "response_mapping": {"type": "code", "path": "response"}
    },
    "creative_writing_mistral": {
        "name": "Mistral AI", "description": "Creative text, conversations, explanations.",
        "base_url": "https://mistral-ai-three.vercel.app/", "method": "GET",
        "params": {"id": "{fullname}", "question": "{prompt}"},
        "response_is_plain_text": True, "response_mapping": {"type": "text","path" : "answer"}
    }
}

# --- Rich UI Templates ---
HTML_TEMPLATES = {
    # note: {filename} will be populated with a timestamped filename for safe download
    "image_preview_card": """<div class="glass-panel p-4 my-4 rounded-lg"><p class="text-sm text-text-secondary mb-2">Image Preview:</p><img src="{url}" class="rounded-md max-w-full"><div class="mt-4"><a href="{url}" download="{filename}" class="tactical-btn py-2 px-4 rounded-md text-sm inline-flex items-center"><svg class="h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V3" /></svg>Download</a></div></div>""",
    "info_card": """<div class="glass-panel border-l-4 border-yellow-400 p-4 my-4 rounded-lg"><p class="text-yellow-200 text-sm font-bold">Important Information</p><p class="text-text-primary text-sm mt-2">{message}</p></div>""",
    "code_project_card": """<div class="glass-panel border-l-4 border-accent-green p-4 my-4 rounded-lg"><p class="text-accent-green text-sm font-bold">Code Project Hosted</p><p class="text-text-primary text-sm mt-2">Your project is now live in a secure sandbox. You can share this link.</p><div class="mt-4"><a href="{url}" target="_blank" class="tactical-btn py-2 px-4 rounded-md text-sm inline-flex items-center"><svg class="h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>View Preview</a></div></div>"""
}

# --- Helper Functions ---
def get_chat_history(chat_id: str):
    if not chat_id:
        return []
    return list(db.chat_histories.find({"chat_id": chat_id}).sort("timestamp", -1).limit(4))

def save_to_history(chat_id: str, user_prompt: str, yuku_response: Dict):
    if not chat_id:
        return
    db.chat_histories.insert_one({"chat_id": chat_id, "role": "user", "content": user_prompt, "timestamp": datetime.now(timezone.utc)})
    db.chat_histories.insert_one({"chat_id": chat_id, "role": "assistant", "content": yuku_response, "timestamp": datetime.now(timezone.utc)})

async def get_router_ai_decision(system_prompt: str) -> Dict:
    """
    Calls the Mistral / router endpoint and tries to parse a JSON decision.
    Uses the 'answer' field from the response JSON when available (per user's request).
    """
    router_url = f"https://mistral-ai-three.vercel.app/?id=yuku-router-v3&question={quote_plus(system_prompt)}"
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(router_url, timeout=45.0)
            res.raise_for_status()
            # Prefer structured JSON 'answer' if available, else try to parse body text
            try:
                payload = res.json()
                # if Mistral returns {"answer": "..."} where answer is JSON string, try to parse it
                answer_raw = payload.get("answer") or payload.get("text") or res.text
                if isinstance(answer_raw, str):
                    decision_str = answer_raw.strip().replace("```json", "").replace("```", "")
                    return json.loads(decision_str)
                elif isinstance(answer_raw, dict):
                    return answer_raw
            except Exception:
                # fallback to direct body
                decision_str = res.text.strip().replace("```json", "").replace("```", "")
                try:
                    return json.loads(decision_str)
                except Exception:
                    return {}
        except Exception:
            return {}

async def choose_tool_and_generate_chips(user_prompt: str, history: List[Dict]) -> Dict:
    tool_descriptions = "\n".join([f"- {name}: {details['description']}" for name, details in TOOL_REGISTRY.items()])
    system_prompt = f"""You are YUKU, an AI assistant. Your role is to assist users with tasks by choosing the best tool. Based on the user's prompt, choose a tool and generate 3 relevant follow-up suggestions ('chips').
Respond ONLY with a valid JSON object: {{"tool_name": "...", "prompt_for_tool": "...", "chips": ["...", "...", "..."]}}.
Tools: {tool_descriptions}
LATEST User Prompt: "{user_prompt}"
"""
    decision = await get_router_ai_decision(system_prompt)
    if not decision.get("tool_name") or decision.get("tool_name") not in TOOL_REGISTRY:
        if any(word in user_prompt.lower() for word in ["draw", "image", "photo", "picture"]):
            decision["tool_name"] = "image_generation_midjourney"
        else:
            decision["tool_name"] = "creative_writing_mistral"
    if not decision.get("prompt_for_tool"):
        decision["prompt_for_tool"] = user_prompt
    if not decision.get("chips"):
        last_word = user_prompt.split()[-1] if user_prompt.split() else user_prompt
        decision["chips"] = [f"Explain '{last_word}' more", "Generate an image for this", "Give a step-by-step plan"]
    return decision

def _extract_by_path(obj: Dict[str, Any], path: str) -> Any:
    """
    Extract nested value by dotted path (e.g., 'data.result.url').
    If path not present returns None.
    """
    if not path:
        return None
    parts = path.split(".")
    cur = obj
    for p in parts:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return None
    return cur

# --- API Endpoints ---
class SandboxRequest(BaseModel):
    files: Dict[str, str]

# NOTE: sandbox host endpoint removed per request (unused). Endpoints preserved.

@router.get("/tools")
async def get_tools_list():
    return TOOL_REGISTRY

@router.post("/ask")
async def ask_yuku_mcp(
    prompt: str = Form(...),
    chat_id: str = Form(...),
    tool_override: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    # If a file is uploaded, include its filename in the prompt context (no local file write)
    if file:
        prompt = f"Using the uploaded file '{file.filename}' as context, the user's prompt is: {prompt}"

    history = get_chat_history(chat_id)
    user_fullname = current_user.get("fullname", "User")  # always prefer fullname for personalization

    if tool_override in TOOL_REGISTRY:
        decision = {"tool_name": tool_override, "prompt_for_tool": prompt}
    else:
        decision = await choose_tool_and_generate_chips(prompt, history)

    chosen_tool = decision.get("tool_name", "creative_writing_mistral")
    prompt_for_tool = decision.get("prompt_for_tool", prompt)
    chips = decision.get("chips", [])

    tool = TOOL_REGISTRY[chosen_tool]
    yuku_response: Dict[str, Any] = {}

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        try:
            # Use fullname in placeholders (encoded), not user id
            placeholders = {"prompt": quote_plus(prompt_for_tool), "fullname": quote_plus(user_fullname)}
            formatted_params = {k: v.format(**placeholders) for k, v in tool.get("params", {}).items()}

            # POST vs GET handling with safer checks
            if tool["method"].upper() == "POST":
                # Some tools expect `message` as a query param even if method is POST (MidJourney style)
                if "message" in tool.get("params", {}):
                    full_url = f"{tool['base_url']}?message={formatted_params.get('message','')}"
                    api_response = await client.post(full_url, headers=tool.get("headers", {}))
                else:
                    api_response = await client.post(tool["base_url"], json=formatted_params, headers=tool.get("headers", {}))
            else:  # GET
                api_response = await client.get(tool["base_url"], params=formatted_params)

            api_response.raise_for_status()

            # IMAGE URL direct responses
            if tool.get("response_is_image_url"):
                # Use final resolved URL (httpx.URL -> str)
                img_url = str(api_response.url)
                # timestamped download filename
                ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                filename = f"yuku_generated_{ts}.png"
                yuku_response = {
                    "type": "html_template",
                    "content": HTML_TEMPLATES["image_preview_card"].format(url=img_url, filename=filename)
                }
            # Plain text responses (Mistral endpoint may return JSON containing 'answer' field)
            elif tool.get("response_is_plain_text"):
                # Attempt to parse JSON and use .get('answer') if present, else raw text
                try:
                    payload = api_response.json()
                    content = payload.get("answer") if isinstance(payload, dict) and payload.get("answer") else api_response.text
                except Exception:
                    content = api_response.text
                yuku_response = {"type": "text", "content": content}
            else:
                data = api_response.json()
                mapping = tool.get("response_mapping", {})
                path = mapping.get("path") if mapping else None
                # support dotted paths
                content = _extract_by_path(data, path) if path else None
                if content is None:
                    # attempt to fall back to entire response or an error message
                    content = data if isinstance(data, (str, dict, list)) else "Error processing response."
                # Special handling for code-generation returning a hosted project JSON
                if chosen_tool == "code_generation" and isinstance(content, str) and content.strip().startswith("{") and '"index.html"' in content:
                    # try to parse project JSON
                    try:
                        parsed = json.loads(content)
                        yuku_response = {"type": "code_project", "content": parsed}
                    except Exception:
                        yuku_response = {"type": "text", "content": content}
                else:
                    # for other cases, if content is dict convert to pretty JSON string for type=text
                    if isinstance(content, (dict, list)):
                        yuku_response = {"type": "text", "content": json.dumps(content, ensure_ascii=False, indent=2)}
                    else:
                        yuku_response = {"type": "text", "content": str(content)}

        except Exception as e:
            # Return the error to user in structured form (per request "provide to user is same err")
            yuku_response = {"type": "error", "content": str(e)}

    yuku_response["source"] = tool["name"]
    yuku_response["chips"] = chips

    save_to_history(chat_id, prompt, yuku_response)
    return {"yuku_response": yuku_response}