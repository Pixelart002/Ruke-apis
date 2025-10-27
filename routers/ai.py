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

router = APIRouter(prefix="/ai", tags=["AI Core"])

# --- RAG Knowledge Base & System Prompts ---
TOOL_REGISTRY = {
    "image_generation_midjourney": {
        "name": "MidJourney",
        "description": "High-quality, artistic images.",
        "base_url": "https://midapi.vasarai.net/api/v1/images/generate-image",
        "method": "POST",
        "headers": {"Authorization": "Bearer vasarai"},
        "params": {"message": "{prompt}"},
        "response_mapping": {"type": "image_url", "path": "cdn_url"}
    },
    "image_generation_flux": {
        "name": "Flux-Schnell",
        "description": "Very fast image generation.",
        "base_url": "https://flux-schnell.hello-kaiiddo.workers.dev/img",
        "method": "GET",
        "params": {"prompt": "{prompt}"},
        "response_is_image_url": True
    },
    "code_generation": {
        "name": "Code Generator",
        "description": "Writes code, creates full websites.",
        "base_url": "https://text.hello-kaiiddo.workers.dev/generate",
        "method": "GET",
        "params": {
            "q": "{prompt}",
            "model": "openai",
            "system": "You are a YUKU AI code generation module. If asked for a website, provide a JSON object with filenames as keys (e.g., 'index.html', 'style.css') and the complete code as string values. For single code snippets, use markdown with language identifiers."
        },
        "response_mapping": {"type": "code", "path": "response"}
    },
    "creative_writing_mistral": {
        "name": "Mistral AI",
        "description": "Creative text, conversations, explanations.",
        "base_url": "https://mistral-ai-three.vercel.app/",
        "method": "GET",
        "params": {"id": "{fullname}", "question": "{prompt}"},
        "response_is_plain_text": True,
        "response_mapping": {"type": "text", "path": "answer"}
    }
}

# --- Rich UI Templates ---
HTML_TEMPLATES = {
    # note: {url} will be appended with ?t={ts} so download and preview are the same resource with timestamp cache-bust
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
    db.chat_histories.insert_one({
        "chat_id": chat_id,
        "role": "user",
        "content": user_prompt,
        "timestamp": datetime.now(timezone.utc)
    })
    db.chat_histories.insert_one({
        "chat_id": chat_id,
        "role": "assistant",
        "content": yuku_response,
        "timestamp": datetime.now(timezone.utc)
    })


async def get_router_ai_decision(system_prompt: str) -> Dict:
    router_url = f"https://mistral-ai-three.vercel.app/?id=yuku-router-v3&question={quote_plus(system_prompt)}"
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(router_url, timeout=45.0)
            res.raise_for_status()
            decision_str = res.text.strip()
            # remove code fences if present
            decision_str = decision_str.replace("```json", "").replace("```", "").strip()
            return json.loads(decision_str)
        except Exception:
            return {}


async def choose_tool_and_generate_chips(user_prompt: str, history: List[Dict]) -> Dict:
    tool_descriptions = "\n".join([f"- {name}: {details['description']}" for name, details in TOOL_REGISTRY.items()])
    # guard empty prompt
    safe_prompt = (user_prompt or "").strip()
    last_word = safe_prompt.split()[-1] if safe_prompt else ""
    system_prompt = f"""You are YUKU, an AI assistant. Your role is to assist users with tasks by choosing the best tool. Based on the user's prompt, choose a tool and generate 3 relevant follow-up suggestions ('chips').
Respond ONLY with a valid JSON object: {{"tool_name": "...", "prompt_for_tool": "...", "chips": ["...", "...", "..."]}}.
Tools: {tool_descriptions}
LATEST User Prompt: "{safe_prompt}"
"""
    decision = await get_router_ai_decision(system_prompt)
    if not decision.get("tool_name") or decision.get("tool_name") not in TOOL_REGISTRY:
        if any(word in safe_prompt.lower() for word in ["draw", "image", "photo", "picture", "generate image", "render"]):
            decision["tool_name"] = "image_generation_midjourney"
        else:
            decision["tool_name"] = "creative_writing_mistral"
    if not decision.get("prompt_for_tool"):
        decision["prompt_for_tool"] = safe_prompt or "Please clarify the user's request."
    if not decision.get("chips"):
        fallback_chip_1 = f"Explain '{last_word}' more" if last_word else "Explain this further"
        decision["chips"] = [fallback_chip_1, "Generate an image for this", "Give step-by-step instructions"]
    return decision

# --- API Endpoints ---


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
    # If file provided, include filename context (no file saving)
    if file:
        prompt = f"Using the uploaded file '{file.filename}' as context, the user's prompt is: {prompt}"

    history = get_chat_history(chat_id)
    user_fullname = current_user.get("fullname", "User")

    if tool_override in TOOL_REGISTRY:
        decision = {"tool_name": tool_override, "prompt_for_tool": prompt}
    else:
        decision = await choose_tool_and_generate_chips(prompt, history)

    chosen_tool = decision.get("tool_name", "creative_writing_mistral")
    prompt_for_tool = decision.get("prompt_for_tool", prompt)
    chips = decision.get("chips", [])

    tool = TOOL_REGISTRY[chosen_tool]
    yuku_response: Dict[str, Any] = {}

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            # placeholders: use quote_plus for safe query values
            placeholders = {
                "prompt": quote_plus(prompt_for_tool or ""),
                "fullname": quote_plus(user_fullname or "")
            }
            formatted_params = {k: v.format(**placeholders) for k, v in tool.get("params", {}).items()}

            # POST vs GET flow
            if tool["method"].upper() == "POST":
                # special-case MidJourney-like endpoints that expect message as query param
                if "message" in formatted_params:
                    full_url = f"{tool['base_url']}?message={formatted_params['message']}"
                    api_response = await client.post(full_url, headers=tool.get("headers", {}))
                else:
                    api_response = await client.post(tool["base_url"], json=formatted_params, headers=tool.get("headers", {}))
            else:  # GET
                # NOTE: formatted_params may contain already-encoded values
                api_response = await client.get(tool["base_url"], params=formatted_params)

            api_response.raise_for_status()

            # timestamp for cache-busting and consistent download filename
            ts = int(datetime.now(timezone.utc).timestamp())

            if tool.get("response_is_image_url"):
                # many image endpoints redirect to a final URL — use the response URL (final)
                img_url = str(api_response.url)
                img_url_with_ts = f"{img_url}?t={ts}"
                filename = f"yuku_{ts}.png"
                html = HTML_TEMPLATES["image_preview_card"].format(url=img_url_with_ts, filename=filename)
                yuku_response = {
                    "type": "html_template",
                    "content": html,
                    "image_url": img_url,
                    "download_url": img_url_with_ts,
                    "download_filename": filename
                }
            elif tool.get("response_is_plain_text"):
                yuku_response = {"type": "text", "content": api_response.text}
            else:
                data = api_response.json()
                # response_mapping.path is a key (flat). If nested path logic is needed later, adapt here.
                mapping = tool.get("response_mapping", {}) or {}
                path = mapping.get("path")
                if path:
                    content = data.get(path, None)
                else:
                    # fallback: entire json
                    content = data

                if chosen_tool == "code_generation" and isinstance(content, str) and content.strip().startswith("{") and '"index.html"' in content:
                    # return parsed project JSON if detected
                    try:
                        yuku_response = {"type": "code_project", "content": json.loads(content)}
                    except Exception:
                        yuku_response = {"type": "text", "content": content}
                else:
                    # ensure content is stringifiable
                    yuku_response = {"type": "text", "content": content if isinstance(content, str) else json.dumps(content)}
        except httpx.HTTPStatusError as he:
            yuku_response = {"type": "error", "content": f"Upstream API HTTP error: {str(he)}"}
        except Exception as e:
            yuku_response = {"type": "error", "content": str(e)}

    yuku_response["source"] = tool["name"]
    yuku_response["chips"] = chips

    save_to_history(chat_id, prompt, yuku_response)
    return {"yuku_response": yuku_response}