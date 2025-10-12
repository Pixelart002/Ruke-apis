import os
import httpx
import json
import uuid
from urllib.parse import quote_plus
from fastapi import APIRouter, Depends, HTTPException, status, Form, UploadFile, File, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List

from auth import utils as auth_utils
from database import db

router = APIRouter(prefix="/ai", tags=["AI Core"])

# Mount a directory to serve sandboxed code previews
# Make sure you have a 'static' folder in your project's root
os.makedirs("static/sandboxed", exist_ok=True)
router.mount("/static", StaticFiles(directory="static"), name="static")


# --- RAG Knowledge Base: The AI Directory of Tools ---
TOOL_REGISTRY = {
    "image_generation_midjourney": {
        "description": "Best for generating high-quality, artistic, and complex images from a text prompt (e.g., 'photo of...', 'draw...', 'cinematic poster...').",
        "base_url": "https://midapi.vasarai.net/api/v1/images/generate-image", "method": "POST",
        "headers": {"Authorization": "Bearer vasarai"}, "params": {"message": "{prompt}"},
        "response_mapping": {"type": "image_url", "path": "cdn_url"}
    },
    "code_generation": {
        "description": "Specialized for writing code, creating full websites with multiple files (HTML, CSS, JS), or explaining code snippets.",
        "base_url": "https://text.hello-kaiiddo.workers.dev/generate", "method": "GET",
        "params": {"q": "{prompt}", "model": "openai", "system": "You are an expert web developer and programmer. When asked to create a website, provide a JSON object with filenames as keys (e.g., 'index.html', 'style.css') and the code as string values. For other code, use markdown."},
        "response_mapping": {"type": "code", "path": "response"}
    },
    "creative_writing": {
        "description": "A powerful model for creative text (poems, stories, scripts) or for answering general questions when no other tool is a good fit. This is the default reasoning tool.",
        "base_url": "https://text.hello-kaiiddo.workers.dev/generate", "method": "GET",
        "params": {"q": "{prompt}", "model": "mistral", "system": "You are YUKU, a highly intelligent and helpful AI assistant. Answer the user's query clearly and concisely."},
        "response_mapping": {"type": "text", "path": "response"}
    }
}

# --- Special HTML Templates for Rich UI ---
HTML_TEMPLATES = {
    "code_block": """<div class="code-block glass-panel rounded-md border border-[var(--border-color)] overflow-hidden my-4"><div class="bg-black/30 px-4 py-2 flex justify-between items-center"><span class="text-xs text-text-secondary">{language}</span><button onclick="navigator.clipboard.writeText(this.closest('.code-block').querySelector('code').innerText)" class="copy-btn text-xs text-text-secondary hover:text-accent-green">Copy</button></div><pre><code class="language-{language} p-4 block text-sm">{code}</code></pre></div>""",
    "download_link": """<div class="my-4"><a href="{url}" download="{filename}" class="tactical-btn py-2 px-4 rounded-md text-sm inline-flex items-center"><svg class="h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V3" /></svg>Download {filename}</a></div>""",
    "info_card": """<div class="glass-panel border-l-4 border-yellow-400 p-4 my-4 rounded-lg"><p class="text-yellow-200 text-sm">{message}</p></div>"""
}

# --- Helper Functions ---
def get_chat_history(chat_id: str) -> List[Dict]:
    if not chat_id: return []
    history_cursor = db.chat_histories.find({"chat_id": chat_id}).sort("timestamp", 1).limit(4)
    return list(history_cursor)

def save_to_history(chat_id: str, user_prompt: str, yuku_response: Dict):
    if not chat_id: return
    db.chat_histories.insert_one({"chat_id": chat_id, "role": "user", "content": user_prompt, "timestamp": datetime.now(timezone.utc)})
    db.chat_histories.insert_one({"chat_id": chat_id, "role": "assistant", "content": yuku_response, "timestamp": datetime.now(timezone.utc)})

async def choose_tool(user_prompt: str, history: List[Dict]) -> Dict:
    tool_descriptions = "\n".join([f"- {name}: {details['description']}" for name, details in TOOL_REGISTRY.items()])
    history_str = "\n".join([f"{msg.get('role', 'user')}: {str(msg.get('content', ''))}" for msg in history])
    
    system_prompt = f"""You are YUKU, an AI dispatcher. Your job is to analyze the user's prompt and chat history to choose the best tool.
    Respond ONLY with a JSON object: {{"tool_name": "...", "prompt_for_tool": "..."}}.
    
    Tools:
    {tool_descriptions}
    
    History:
    {history_str}
    
    LATEST User Prompt: "{user_prompt}"
    """
    router_url = f"https://text.hello-kaiiddo.workers.dev/generate?model=mistral&q={quote_plus(system_prompt)}"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(router_url)
            response.raise_for_status()
            data = response.json()
            decision_str = data.get("response", "{}").strip().replace("```json", "").replace("```", "")
            return json.loads(decision_str)
        except Exception:
            return {"tool_name": "creative_writing", "prompt_for_tool": user_prompt}

# --- API Endpoints ---
class SandboxRequest(BaseModel):
    files: Dict[str, str]

@router.post("/sandbox/host")
async def host_sandboxed_code(req: SandboxRequest, current_user: Dict = Depends(auth_utils.get_current_user)):
    slug = str(uuid.uuid4())
    project_path = os.path.join("static/sandboxed", slug)
    os.makedirs(project_path, exist_ok=True)

    if not req.files or "index.html" not in req.files:
        raise HTTPException(status_code=400, detail="index.html is required.")

    for filename, content in req.files.items():
        # Basic sanitization
        if ".." in filename or filename.startswith("/"):
            raise HTTPException(status_code=400, detail="Invalid filename.")
        with open(os.path.join(project_path, filename), "w", encoding="utf-8") as f:
            f.write(content)
            
    preview_url = f"/ai/static/sandboxed/{slug}/index.html"
    return {"status": "ok", "preview_url": preview_url, "slug": slug}

@router.post("/ask")
async def ask_yuku_mcp(prompt: str = Form(...), chat_id: str = Form(...), file: Optional[UploadFile] = File(None), current_user: Dict = Depends(auth_utils.get_current_user)):
    if file:
        prompt = f"User uploaded '{file.filename}'. The prompt is: {prompt}"

    history = get_chat_history(chat_id)
    decision = await choose_tool(prompt, history)
    chosen_tool = decision.get("tool_name", "creative_writing")
    prompt_for_tool = decision.get("prompt_for_tool", prompt)
    
    if chosen_tool not in TOOL_REGISTRY: chosen_tool = "creative_writing"
    
    tool = TOOL_REGISTRY[chosen_tool]
    yuku_response = {}
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            url, headers = tool["base_url"], tool.get("headers", {})
            params = {k: v.format(prompt=quote_plus(prompt_for_tool)) for k,v in tool.get("params", {}).items()}
            full_url = f"{url}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"
            
            api_response = await client.get(full_url, headers=headers) if tool["method"] == "GET" else await client.post(full_url, headers=headers)
            api_response.raise_for_status()

            if tool.get("response_is_image_url"):
                img_url = str(api_response.url)
                yuku_response = {
                    "type": "html_template",
                    "content": HTML_TEMPLATES["download_link"].format(url=img_url, filename="generated_image.png")
                }
            else:
                data = api_response.json()
                content = data.get(tool["response_mapping"]["path"], "Sorry, I couldn't process that.")
                
                # Check if the content is a JSON string representing a file structure
                if content.strip().startswith("{") and '"index.html"' in content:
                    yuku_response = {"type": "code_project", "content": json.loads(content)}
                else:
                    yuku_response = {"type": "text", "content": content}

        except Exception as e:
            yuku_response = {"type": "error", "content": f"An external API error occurred: {str(e)}"}
    
    yuku_response["source"] = chosen_tool
    yuku_response["chips"] = [f"Tell me more about {prompt.split()[-1]}", "Generate an image for this", "Explain this code"]
    
    save_to_history(chat_id, prompt, yuku_response)
    return {"yuku_response": yuku_response}





