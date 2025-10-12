import os
import httpx
import json
from urllib.parse import quote_plus
from fastapi import APIRouter, Depends, HTTPException, status, Form, UploadFile, File
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from auth import utils as auth_utils
from database import db
from bson import ObjectId

router = APIRouter(prefix="/ai", tags=["AI Core"])

# --- RAG Knowledge Base: The AI Directory of Tools ---
TOOL_REGISTRY = {
    "image_generation_midjourney": {
        "description": "Best for generating high-quality, artistic, and complex images from a text prompt. Use for prompts like 'photo of...', 'draw...', 'create an image of...', 'robot lion', 'cinematic poster...'.",
        "base_url": "https://midapi.vasarai.net/api/v1/images/generate-image",
        "method": "POST",
        "headers": {"Authorization": "Bearer vasarai"},
        "params": {"message": "{prompt}"},
        "response_mapping": {"type": "image_url", "path": "cdn_url"}
    },
    "image_generation_flux": {
        "description": "Best for generating images very quickly or when Midjourney fails. Use for simple prompts or when speed is important.",
        "base_url": "https://flux-schnell.hello-kaiiddo.workers.dev/img",
        "method": "GET",
        "params": {"prompt": "{prompt}"},
        "response_is_image_url": True 
    },
    "code_generation": {
        "description": "Specialized for writing code in any language, creating websites with HTML/CSS/JS, or explaining code snippets. Use for prompts like 'write a python function...', 'create a login page html...'.",
        "base_url": "https://text.hello-kaiiddo.workers.dev/generate",
        "method": "GET",
        "params": {"q": "{prompt}", "model": "openai", "system": "You are an expert programmer. Provide only the code block requested, with language identifier. Do not add any extra explanations unless asked."},
        "response_mapping": {"type": "code", "path": "response"}
    },
    "creative_writing": {
        "description": "A powerful model for creative text generation like writing poems, stories, scripts, or detailed explanations. Use for complex writing tasks.",
        "base_url": "https://text.hello-kaiiddo.workers.dev/generate",
        "method": "GET",
        "params": {"q": "{prompt}", "model": "mistral", "system": "You are a helpful and creative assistant named YUKU."},
        "response_mapping": {"type": "text", "path": "response"}
    },
    "web_search": {
        "description": "Best for answering questions that require up-to-date, factual information or searching the web. Use for prompts like 'what is...', 'who is...', 'latest news on...'.",
        "base_url": "https://search.hello-kaiiddo.workers.dev/search",
        "method": "GET",
        "params": {"q": "{prompt}"},
        "response_mapping": {"type": "text", "path": "response"}
    },
    "simple_chat": {
        "description": "A general-purpose chatbot for simple conversations, greetings, or when no other tool is a good fit. This is the default fallback tool.",
        "base_url": "https://qwen.a3z.workers.dev/api/completions",
        "method": "POST",
        "params": {"content": "{prompt}"},
        "response_mapping": {"type": "text", "path": "message"}
    }
}

HTML_TEMPLATES = {
    "code_block": """
    <div class="code-block glass-panel rounded-md border border-[var(--border-color)] overflow-hidden">
        <div class="bg-black/30 px-4 py-2 flex justify-between items-center">
            <span class="text-xs text-text-secondary">{language}</span>
            <button class="copy-btn text-xs text-text-secondary hover:text-accent-green">Copy</button>
        </div>
        <pre><code class="language-{language} p-4 block text-sm">{code}</code></pre>
    </div>
    """
}

# --- Helper Functions ---
# CHANGE 1: 'async def' is now 'def'
def _get_chat_history(chat_id: str) -> List[Dict]:
    """Fetches and returns the last 4 messages from the chat history."""
    if not chat_id:
        return []
    history_cursor = db.chat_histories.find({"chat_id": chat_id}).sort("timestamp", 1).limit(4)
    # CHANGE 2: 'await' is removed
    return list(history_cursor)

# CHANGE 3: 'async def' is now 'def'
def _save_to_history(chat_id: str, user_prompt: str, yuku_response: Dict):
    """Saves the user prompt and YUKU's response to the database."""
    if not chat_id:
        return
    
    # Save user message
    db.chat_histories.insert_one({
        "chat_id": chat_id,
        "role": "user",
        "content": user_prompt,
        "timestamp": datetime.now(timezone.utc)
    })
    
    # Save assistant response
    db.chat_histories.insert_one({
        "chat_id": chat_id,
        "role": "assistant",
        "content": yuku_response,
        "timestamp": datetime.now(timezone.utc)
    })

async def _choose_tool(user_prompt: str, history: List[Dict]) -> Dict:
    tool_descriptions = "\n".join([f"- {name}: {details['description']}" for name, details in TOOL_REGISTRY.items()])
    history_str = "\n".join([f"{msg.get('role', 'user')}: {msg.get('content', '')}" for msg in history])
    system_prompt = f"""
    You are YUKU, an AI dispatcher. Your job is to analyze the user's prompt and chat history to choose the best tool from the list below.
    Respond ONLY with a JSON object containing "tool_name" and "prompt_for_tool".

    Available Tools:
    {tool_descriptions}

    Chat History (for context):
    {history_str}

    Based on the history and the LATEST user prompt, make a decision.
    User Prompt: "{user_prompt}"
    """
    router_url = f"https://text.hello-kaiiddo.workers.dev/generate?model=mistral&q={quote_plus(system_prompt)}"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(router_url)
            response.raise_for_status()
            data = response.json()
            decision_str = data.get("response", "{}").strip().replace("```json", "").replace("```", "")
            decision = json.loads(decision_str)
            return decision
        except Exception as e:
            return {"tool_name": "simple_chat", "prompt_for_tool": user_prompt}

# --- The New Master Endpoint ---
@router.post("/ask")
async def ask_yuku_mcp(
    prompt: str = Form(...),
    chat_id: str = Form(...),
    file: Optional[UploadFile] = File(None),
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    if file:
        prompt = f"User uploaded a file named '{file.filename}'. The text prompt is: {prompt}"

    history = _get_chat_history(chat_id)
    decision = await _choose_tool(prompt, history)
    
    chosen_tool_name = decision.get("tool_name", "simple_chat")
    prompt_for_tool = decision.get("prompt_for_tool", prompt)
    
    if chosen_tool_name not in TOOL_REGISTRY:
        chosen_tool_name = "simple_chat"

    tool = TOOL_REGISTRY[chosen_tool_name]
    final_response = {}
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            url = tool["base_url"]
            headers = tool.get("headers", {})
            params = {k: v.format(prompt=quote_plus(prompt_for_tool)) for k, v in tool.get("params", {}).items()}
            
            full_url = f"{url}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"

            if tool["method"] == "POST":
                api_response = await client.post(full_url, headers=headers)
            else: # GET request
                api_response = await client.get(full_url, headers=headers)
            
            api_response.raise_for_status()

            if tool.get("response_is_image_url"):
                final_response = {"type": "image_url", "content": str(api_response.url)}
            else:
                data = api_response.json()
                mapping = tool["response_mapping"]
                content = data.get(mapping["path"], "Sorry, I couldn't process that.")
                if "```" in content and mapping["type"] == "code":
                    try:
                        lang = content.split("```")[1].split("\n")[0].strip()
                        code = "\n".join(content.split("\n")[1:-1])
                        final_content = HTML_TEMPLATES["code_block"].format(language=lang, code=code)
                        final_response = {"type": "html_template", "content": final_content}
                    except Exception:
                        final_response = {"type": "text", "content": content}
                else:
                    final_response = {"type": "text", "content": content}

        except Exception as e:
            final_response = {"type": "error", "content": f"An external API error occurred: {str(e)}"}
    
    final_response["source"] = chosen_tool_name
    _save_to_history(chat_id, prompt, final_response)
    
    return { "yuku_response": final_response, "original_prompt": prompt }

