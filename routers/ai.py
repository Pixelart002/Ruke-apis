# routers/ai.py

import os
import time
import json
import logging
import urllib.parse
import base64
import io
import secrets
import zipfile
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

# --- LIBRARIES ---
import httpx
from PIL import Image
from duckduckgo_search import DDGS 
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel
from bson import ObjectId

# --- OPTIONAL IMPORTS ---
try:
    import pypdf
except ImportError:
    pypdf = None

# --- LOCAL IMPORTS ---
from auth import utils as auth_utils 
from database import db

# --- CONFIG ---
logger = logging.getLogger("AI_CORE")
logger.setLevel(logging.INFO)
router = APIRouter(prefix="/ai", tags=["AI Core"])

# --- CONSTANTS ---
# Update this with your deployed backend URL if needed
BACKEND_URL = os.getenv("BACKEND_URL", "https://giant-noell-pixelart002-1c1d1fda.koyeb.app")
PISTON_API = "https://emkc.org/api/v2/piston/execute"

# --- SYSTEM PROMPTS ---
VFS_PROMPT = """
You are YUKU, an Expert AI Full-Stack Architect.
You operate a Virtual File System (VFS).

CRITICAL RULES FOR FILE CONTENT:
1. **index.html**: Must contain ONLY valid HTML5 code. 
   - Link CSS: <link rel="stylesheet" href="style.css">
   - Link JS: <script src="script.js"></script>
   
2. **style.css**: Must contain ONLY raw CSS rules. 
   - PROHIBITED: Do NOT use <style> tags. Do NOT write HTML.
   
3. **script.js**: Must contain ONLY raw JavaScript. 
   - PROHIBITED: Do NOT use <script> tags. Do NOT write HTML.

4. **JSON Output**: Return a valid JSON object wrapped in ```json ... ``` blocks.

FORMAT:
{
  "message": "Creating project...",
  "operations": [
    { "action": "create", "path": "index.html", "content": "<!DOCTYPE html>..." },
    { "action": "create", "path": "style.css", "content": "body { background: #000; }" },
    { "action": "create", "path": "script.js", "content": "console.log('Ready');" }
  ]
}
"""

# --- MODELS ---
class AgentModel(BaseModel):
    name: str
    slug: str
    system_prompt: str
    description: str = "Custom Agent"

class MemoryModel(BaseModel):
    memory: str

class CodeRunRequest(BaseModel):
    language: str
    code: str

# --- HELPER FUNCTIONS ---

def get_collection(name: str):
    if db is None: 
        raise HTTPException(500, "DB Disconnected")
    return db[name]

async def parse_files(file: UploadFile) -> str:
    """Extracts text from uploaded files (PDF, Images, Text)."""
    content = ""
    fname = file.filename.lower()
    try:
        data = await file.read()
        if fname.endswith(".pdf") and pypdf:
            r = pypdf.PdfReader(io.BytesIO(data))
            for p in r.pages: 
                content += p.extract_text() + "\n"
        elif fname.endswith(('.png', '.jpg', '.webp')):
            try:
                img = Image.open(io.BytesIO(data))
                content += f"\n[IMAGE METADATA: {fname} | Size: {img.size}]\n"
            except:
                content += f"\n[IMAGE ATTACHED: {fname}]\n"
        else: 
            content = data.decode('utf-8', errors='ignore')
    except Exception as e:
        logger.error(f"Error reading file {fname}: {e}")
        return f"[Error reading {fname}]"
    return f"\n=== FILE: {fname} ===\n{content}\n"

def perform_web_search(query: str) -> str:
    """Performs a synchronous web search using DuckDuckGo."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
            if not results: return ""
            summary = "\n[WEB DATA]:\n"
            for r in results: 
                summary += f"- {r['title']}: {r['body']}\n"
            return summary
    except Exception as e:
        logger.error(f"Search Error: {e}") 
        return ""

async def call_pollinations(prompt: str, system: str) -> str:
    """Calls Pollinations AI for text generation."""
    full = f"{system}\n\nUSER: {prompt}\n\nASSISTANT:"
    url = f"https://text.pollinations.ai/{urllib.parse.quote(full)}?model=openai&seed={secrets.randbelow(9999)}"
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            r = await client.get(url)
            return r.text.strip()
        except Exception as e:
            logger.error(f"Pollinations API Error: {e}")
            return json.dumps({"message": "AI Error: Could not generate response.", "operations": []})

def sanitize_content(path: str, content: str) -> str:
    """Removes Markdown wrappers and prevents HTML injection in CSS/JS."""
    path = path.lower()
    
    # Remove Markdown code blocks
    content = re.sub(r'^```\w*\n', '', content)
    content = re.sub(r'\n```$', '', content)
    
    # Clean CSS
    if path.endswith('.css'):
        content = re.sub(r'<style[^>]*>', '', content, flags=re.I)
        content = re.sub(r'</style>', '', content, flags=re.I)
        content = re.sub(r'<[^>]+>', '', content) 
    
    # Clean JS
    elif path.endswith('.js') or path.endswith('.jsx'):
        content = re.sub(r'<script[^>]*>', '', content, flags=re.I)
        content = re.sub(r'</script>', '', content, flags=re.I)

    return content.strip()

def process_vfs(text: str, vfs: dict) -> tuple[str, dict, bool]:
    """Parses JSON from AI response and updates the Virtual File System."""
    new_vfs = vfs.copy()
    # Regex to find JSON block
    match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
    if not match: 
        match = re.search(r'(\{.*"operations":.*\})', text, re.DOTALL)
    
    updated = False
    msg = text
    
    if match:
        try:
            json_str = match.group(1)
            json_str = json_str.replace('\\n', '\\\\n') # Fix common JSON escape issue
            
            data = json.loads(json_str)
            msg = data.get("message", "Code updated.")
            
            for op in data.get("operations", []):
                path = op['path'].strip('/')
                raw_content = op['content']
                
                # Apply Strict Sanitization
                clean_content = sanitize_content(path, raw_content)
                
                updated = True
                if op['action'] in ['create', 'update']: 
                    new_vfs[path] = clean_content
                elif op['action'] == 'delete' and path in new_vfs: 
                    del new_vfs[path]
        except Exception as e:
            logger.error(f"VFS Parsing Error: {e}")
            
    return msg, new_vfs, updated

def inject_assets(html: str, vfs: dict) -> str:
    """Injects CSS and JS directly into HTML for single-page preview."""
    if not html: return "<h1>Error: Empty HTML</h1>"
    
    for path, code in vfs.items():
        name = path.split('/')[-1]
        
        if path.endswith('.css'):
            # Replace <link ... href="style.css"> with <style>...</style>
            pattern = re.compile(f'<link[^>]*href=["\'].*?{re.escape(name)}["\'][^>]*>', re.IGNORECASE)
            if pattern.search(html):
                html = pattern.sub(f'<style>/* {path} */\n{code}</style>', html)
        
        if path.endswith('.js'):
            # Replace <script ... src="script.js"> with <script>...</script>
            pattern = re.compile(f'<script[^>]*src=["\'].*?{re.escape(name)}["\'][^>]*>.*?</script>', re.IGNORECASE | re.DOTALL)
            if pattern.search(html):
                html = pattern.sub(f'<script>/* {path} */\n{code}</script>', html)
            
    return html

# --- CORE ENDPOINTS ---

@router.post("/ask")
async def ask_ai(
    prompt: str = Form(...),
    tool_id: str = Form("mistral_default"),
    chat_id: Optional[str] = Form(None),
    files: List[UploadFile] = File(None),
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    chats = get_collection("chat_history")
    
    # 1. Handle Files
    file_ctx = ""
    if files:
        for f in files: 
            file_ctx += await parse_files(f)

    # 2. Handle Web Search (Triggers on keywords)
    search_ctx = ""
    if any(t in prompt.lower() for t in ["search", "news", "latest", "price", "weather"]):
        search_ctx = perform_web_search(prompt)

    # 3. Load Chat State
    vfs = {}
    memory = ""
    if chat_id and ObjectId.is_valid(chat_id):
        c = chats.find_one({"_id": ObjectId(chat_id)})
        if c:
            vfs = c.get("vfs_state", {})
            memory = c.get("memory", "")

    # 4. Determine System Prompt
    agent = get_collection("ai_agents").find_one({"slug": tool_id})
    sys_prompt = agent["system_prompt"] if agent else VFS_PROMPT
    sys_prompt += f"\nMEMORY: {memory}"
    
    if "code" in tool_id or "ide" in tool_id:
        sys_prompt += f"\nCURRENT FILES: {json.dumps(list(vfs.keys()))}"

    # 5. Construct Final Prompt
    final_prompt = f"USER: {current_user['fullname']}\nFILES: {file_ctx}\nWEB: {search_ctx}\nQUERY: {prompt}"
    
    # 6. Call AI
    raw_response = await call_pollinations(final_prompt, sys_prompt)
    
    # 7. Process VFS (Code Generation)
    clean_response, vfs, updated = process_vfs(raw_response, vfs)

    # 8. Save History
    msg = {
        "role": "ai", 
        "content": clean_response, 
        "ts": datetime.now(timezone.utc), 
        "vfs_updated": updated
    }
    
    if chat_id and ObjectId.is_valid(chat_id):
        # Push user message first
        chats.update_one({"_id": ObjectId(chat_id)}, 
            {"$push": {"messages": {"role": "user", "content": prompt}}, "$set": {"vfs_state": vfs}})
        # Push AI response
        chats.update_one({"_id": ObjectId(chat_id)}, {"$push": {"messages": msg}})
        fid = chat_id
    else:
        # Create new chat
        r = chats.insert_one({
            "user_id": str(current_user["_id"]), 
            "title": prompt[:30], 
            "vfs_state": vfs, 
            "memory": "", 
            "messages": [msg]
        })
        fid = str(r.inserted_id)

    return {
        "status": "success", 
        "chat_id": fid, 
        "response": clean_response, 
        "vfs": vfs, 
        "data": msg
    }

@router.post("/generate-image")
async def generate_image(
    prompt: str = Form(...), 
    current_user: Dict = Depends(auth_utils.get_current_user), 
    chat_id: Optional[str] = Form(None)
):
    # 1. Enhance Prompt
    enhanced = await call_pollinations(f"Enhance for image generation: {prompt}", "You are a Prompt Engineer.")
    
    # 2. Generate via Flux Schnell
    timestamp = str(int(time.time()))
    encoded_prompt = urllib.parse.quote(enhanced)
    url = f"https://flux-schnell.hello-kaiiddo.workers.dev/img?prompt={encoded_prompt}&t={timestamp}"
    
    try:
        async with httpx.AsyncClient() as c:
            r = await c.get(url, timeout=60.0)
            if r.status_code != 200:
                raise Exception("Image generation failed upstream")
            b64 = base64.b64encode(r.content).decode()
            data_uri = f"data:image/jpeg;base64,{b64}"
    except Exception as e: 
        logger.error(f"Flux Error: {e}")
        raise HTTPException(503, "Image generation service unavailable")
    
    msg = {
        "role": "flux", 
        "content": prompt, 
        "image_data": data_uri, 
        "ts": datetime.now(timezone.utc)
    }
    
    if chat_id and ObjectId.is_valid(chat_id):
        get_collection("chat_history").update_one(
            {"_id": ObjectId(chat_id)}, 
            {"$push": {"messages": msg}}
        )
        
    return {"status": "success", "image_url": data_uri}

# --- DEVOPS & PREVIEW ---

@router.post("/publish/{chat_id}")
async def publish_project(chat_id: str, u: Dict = Depends(auth_utils.get_current_user)):
    """Publishes the VFS state to a permanent URL."""
    c = get_collection("chat_history").find_one({"_id": ObjectId(chat_id)})
    if not c: raise HTTPException(404, "Chat not found")
    
    deployment_id = secrets.token_urlsafe(6)
    get_collection("deployments").insert_one({
        "did": deployment_id, 
        "vfs": c.get("vfs_state", {}), 
        "uid": str(u["_id"]),
        "created_at": datetime.now(timezone.utc)
    })
    
    return {"url": f"{BACKEND_URL}/ai/view/{deployment_id}"}

@router.get("/view/{did}")
async def view_deployment(did: str):
    """Public endpoint to view a deployed project."""
    d = get_collection("deployments").find_one({"did": did})
    if not d: return HTMLResponse("<h1>404 - Deployment Not Found</h1>", 404)
    
    vfs = d["vfs"]
    html = vfs.get("index.html", "<h1>No index.html found in this project.</h1>")
    return HTMLResponse(inject_assets(html, vfs))

@router.get("/live/{chat_id}")
async def live_preview(chat_id: str):
    """Live preview of a chat's VFS state with console log injection."""
    c = get_collection("chat_history").find_one({"_id": ObjectId(chat_id)})
    if not c: return HTMLResponse("Project Not Found", 404)
    
    vfs = c.get("vfs_state", {})
    
    if "index.html" not in vfs:
        return HTMLResponse("<h2 style='color:white; font-family:sans-serif; text-align:center; margin-top:20%'>No index.html generated yet.<br>Ask AI to create a website.</h2>")
        
    html = vfs.get("index.html")
    
    # Console Log Capture Script
    js_capture = """<script>
    (function(){
        const s=window.parent.postMessage.bind(window.parent);
        console.log=(...a)=>s({type:'log',args:a},'*');
        console.error=(...a)=>s({type:'error',args:a},'*');
    })();</script>"""
    
    if "<head>" in html: 
        html = html.replace("<head>", f"<head>{js_capture}")
    else: 
        html = js_capture + html
    
    return HTMLResponse(inject_assets(html, vfs))

# --- TOOLS & UTILITIES ---

@router.post("/run-code")
async def run_code(r: CodeRunRequest):
    """Executes Python/JS code via Piston API."""
    version = "18.15.0" if r.language == "javascript" else "3.10.0"
    payload = {
        "language": r.language,
        "version": version,
        "files": [{"content": r.code}]
    }
    
    async with httpx.AsyncClient() as c:
        try:
            res = await c.post(PISTON_API, json=payload, timeout=10.0)
            return res.json()
        except Exception as e:
            return {"run": {"output": f"Execution Error: {str(e)}"}}

@router.post("/chats/new")
def create_chat(u: Dict = Depends(auth_utils.get_current_user)):
    r = get_collection("chat_history").insert_one({
        "user_id": str(u["_id"]), 
        "title": "New Project", 
        "vfs_state": {}, 
        "messages": []
    })
    return {"chat_id": str(r.inserted_id)}

@router.get("/chats")
def list_chats(u: Dict = Depends(auth_utils.get_current_user)):
    c = get_collection("chat_history").find(
        {"user_id": str(u["_id"])}
    ).sort("_id", -1).limit(30)
    return [{"id": str(x["_id"]), "title": x.get("title", "Untitled")} for x in c]

@router.get("/chats/{chat_id}")
def get_chat(chat_id: str):
    c = get_collection("chat_history").find_one({"_id": ObjectId(chat_id)})
    if not c: raise HTTPException(404, "Chat not found")
    c["id"] = str(c["_id"])
    del c["_id"]
    return c

@router.get("/health")
async def health_check():
    s = time.perf_counter()
    db_status = "connected"
    try: 
        db.command("ping")
    except: 
        db_status = "disconnected"
        
    return {
        "status": "ok", 
        "latency_us": int((time.perf_counter()-s)*1000000), 
        "db": db_status
    }