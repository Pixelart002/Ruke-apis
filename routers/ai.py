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

router = APIRouter(prefix="/ai", tags=["AI Core"])

# --- Tool Registry ---
TOOL_REGISTRY = {
    "image_generation_midjourney": {
        "name": "MidJourney",
        "description": "High-quality, artistic images.",
        "base_url": "https://midapi.vasarai.net/api/v1/images/generate-image",
        "method": "POST",
        "headers": {"Authorization": "Bearer vasarai"},
        "params": {"message": "{prompt}"},
        "response_mapping": {"type": "image_url", "path": "cdn_url"},
    },
    "image_generation_flux": {
        "name": "Flux-Schnell",
        "description": "Very fast image generation.",
        "base_url": "https://flux-schnell.hello-kaiiddo.workers.dev/img",
        "method": "GET",
        "params": {"prompt": "{prompt}"},
        "response_is_image_url": True,
    },
    "code_generation": {
        "name": "Code Generator",
        "description": "Writes code, creates full websites.",
        "base_url": "https://text.hello-kaiiddo.workers.dev/generate",
        "method": "GET",
        "params": {
            "q": "{prompt}",
            "model": "openai",
            "system": (
                "You are a YUKU AI code generation module. If asked for a website, "
                "provide a JSON object with filenames as keys (e.g., 'index.html', 'style.css') "
                "and the complete code as string values. For single code snippets, use markdown."
            ),
        },
        "response_mapping": {"type": "code", "path": "response"},
    },
    "creative_writing_mistral": {
        "name": "Mistral AI",
        "description": "Creative text, conversations, explanations.",
        "base_url": "https://mistral-ai-three.vercel.app/",
        "method": "GET",
        "params": {"id": "{fullname}", "question": "{prompt}"},
        "response_is_plain_text": True,
        "response_mapping": {"type": "text", "path": "answer"},
    },
}

# --- HTML Templates (Enhanced) ---
HTML_TEMPLATES = {
    "image_preview_card": """
    <div class="glass-panel backdrop-blur-lg bg-[#0d0d0d80] p-4 my-4 rounded-2xl shadow-xl border border-gray-700">
        <h3 class="text-lg font-semibold text-white mb-2">🖼️ Generated Image Preview</h3>
        <img src="{url}" alt="Generated Image" class="rounded-xl border border-gray-600 max-w-full mx-auto">
        <div class="flex justify-between items-center mt-4">
            <p class="text-gray-400 text-xs">Generated at: {timestamp}</p>
            <a href="{url}" download="{filename}" 
               class="bg-gradient-to-r from-purple-500 to-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:opacity-90">
               ⬇️ Download
            </a>
        </div>
    </div>
    """,
    "info_card": """
    <div class="glass-panel border-l-4 border-yellow-400 p-4 my-4 rounded-xl bg-[#1a1a1a80] shadow-md">
        <p class="text-yellow-300 text-sm font-bold">⚠️ Important Info</p>
        <p class="text-gray-300 text-sm mt-2">{message}</p>
    </div>
    """,
}

# --- Chat Utilities ---
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

# --- AI Router Decision Engine ---
async def get_router_ai_decision(system_prompt: str) -> Dict:
    """Gets structured JSON decision from Mistral router API."""
    router_url = f"https://mistral-ai-three.vercel.app/?id=yuku-router-v3&question={quote_plus(system_prompt)}"
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(router_url, timeout=45.0)
            res.raise_for_status()
            data = res.json()
            answer_text = data.get("answer", "").replace("\\n", "\n").strip()
            return json.loads(answer_text) if answer_text else {}
        except Exception:
            return {}

async def choose_tool_and_generate_chips(user_prompt: str, history: List[Dict]) -> Dict:
    """Selects best tool and generates smart chip suggestions."""
    tool_descriptions = "\n".join(
        [f"- {name}: {details['description']}" for name, details in TOOL_REGISTRY.items()]
    )
    system_prompt = f"""
You are YUKU, an AI assistant. Based on user input, select the most suitable tool and generate 3 relevant suggestions.
Respond ONLY with valid JSON:
{{"tool_name": "...", "prompt_for_tool": "...", "chips": ["...", "...", "..."]}}
Tools: {tool_descriptions}
User Prompt: "{user_prompt}"
    """.strip()

    decision = await get_router_ai_decision(system_prompt)
    if not decision.get("tool_name") or decision["tool_name"] not in TOOL_REGISTRY:
        decision["tool_name"] = (
            "image_generation_midjourney"
            if any(x in user_prompt.lower() for x in ["draw", "image", "photo"])
            else "creative_writing_mistral"
        )
    decision.setdefault("prompt_for_tool", user_prompt)
    decision.setdefault("chips", ["Explain more", "Generate image", "Summarize it"])
    return decision

# --- Main Ask Endpoint ---
@router.post("/ask")
async def ask_yuku_mcp(
    prompt: str = Form(...),
    chat_id: str = Form(...),
    tool_override: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    current_user: Dict = Depends(auth_utils.get_current_user),
):
    """Unified endpoint for handling all AI requests (chat, image, code)."""
    if file:
        prompt = f"Using uploaded file '{file.filename}', user's prompt: {prompt}"

    history = get_chat_history(chat_id)
    user_fullname = current_user.get("fullname", "User")

    decision = (
        {"tool_name": tool_override, "prompt_for_tool": prompt}
        if tool_override in TOOL_REGISTRY
        else await choose_tool_and_generate_chips(prompt, history)
    )

    chosen_tool = decision.get("tool_name", "creative_writing_mistral")
    prompt_for_tool = decision.get("prompt_for_tool", prompt)
    chips = decision.get("chips", [])
    tool = TOOL_REGISTRY[chosen_tool]

    yuku_response = {}

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            placeholders = {"prompt": quote_plus(prompt_for_tool), "fullname": quote_plus(user_fullname)}
            formatted_params = {k: v.format(**placeholders) for k, v in tool.get("params", {}).items()}

            # Perform API request
            if tool["method"] == "POST":
                api_response = await client.post(
                    tool["base_url"], json=formatted_params, headers=tool.get("headers", {})
                )
            else:
                api_response = await client.get(tool["base_url"], params=formatted_params)

            api_response.raise_for_status()

            # Response Handling
            if tool.get("response_is_image_url"):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                img_url = str(api_response.url)
                filename = f"yuku_generated_{timestamp}.png"
                yuku_response = {
                    "type": "html_template",
                    "content": HTML_TEMPLATES["image_preview_card"].format(
                        url=img_url, filename=filename, timestamp=timestamp
                    ),
                }
            elif tool.get("response_is_plain_text"):
                content = api_response.text.replace("\\n", "\n").strip()
                yuku_response = {"type": "text", "content": content}
            else:
                data = api_response.json()
                path = tool["response_mapping"]["path"]
                content = data.get(path, "Error processing response.")
                yuku_response = {"type": "text", "content": content}

        except Exception as e:
            yuku_response = {"type": "error", "content": f"⚠️ {str(e)}"}

    yuku_response["source"] = tool["name"]
    yuku_response["chips"] = chips

    save_to_history(chat_id, prompt, yuku_response)
    return {"yuku_response": yuku_response}