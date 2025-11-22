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
from PIL import Image
import httpx
from duckduckgo_search import DDGS 
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel
from bson import ObjectId

# --- OPTIONAL IMPORTS ---
try: import pypdf
except: pypdf = None

from auth import utils as auth_utils 
from database import db

# --- CONFIG ---
logger = logging.getLogger("AI_CORE_LEGACY")
logger.setLevel(logging.INFO)
router = APIRouter(prefix="/ai", tags=["AI Core Legacy"])

# --- CONSTANTS ---
BACKEND_URL = "https://giant-noell-pixelart002-1c1d1fda.koyeb.app"
PISTON_API = "https://emkc.org/api/v2/piston/execute"

# --- FILE READING HELPER ---
def read_config_file(path: str, default_value: str) -> str:
    """Dynamically reads prompt files from the config folder."""
    try:
        clean_path = path.lstrip("/") 
        if os.path.exists(clean_path):
            with open(clean_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content: return content
    except Exception as e:
        logger.error(f"Error reading config file {path}: {e}")
    return default_value

# --- SINGLE GOD MODE PROMPT (DYNAMIC LOAD) ---
DEFAULT_GOD_PROMPT = """You are YUKU, the Ultimate AI Developer."""
GOD_MODE_PROMPT = read_config_file("config/prompt.txt", DEFAULT_GOD_PROMPT)

# --- MODELS ---
class MemoryModel(BaseModel):
    memory: str

class CodeRunRequest(BaseModel):
    language: str
    code: str

# --- HELPER FUNCTIONS ---
def get_collection(name: str):
    if db is None: raise HTTPException(500, "DB Disconnected")
    return db[name]

async def parse_files(file: UploadFile) -> str:
    content = ""
    fname = file.filename.lower()
    try:
        data = await file.read()
        if fname.endswith(".pdf") and pypdf:
            r = pypdf.PdfReader(io.BytesIO(data))
            for p in r.pages: content += p.extract_text() + "\n"
        elif fname.endswith(('.png', '.jpg', '.webp')):
            img = Image.open(io.BytesIO(data))
            content += f"\n[IMAGE METADATA: {fname} | Size: {img.size}]\n"
        else: content = data.decode('utf-8', errors='ignore')
    except: return f"[Error reading {fname}]"
    return f"\n=== FILE: {fname} ===\n{content}\n"

def perform_web_search(query: str) -> str:
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
            if not results: return ""
            summary = "\n[WEB DATA]:\n"
            for r in results: summary += f"- {r['title']}: {r['body']}\n"
            return summary
    except Exception as e:
        print(f"Search Error: {e}") 
        return ""

async def call_pollinations(prompt: str, system: str) -> str:
    full = f"{system}\n\nUSER: {prompt}\n\nASSISTANT:"
    url = f"https://text.pollinations.ai/{urllib.parse.quote(full)}?model=openai&seed={secrets.randbelow(9999)}"
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            r = await client.get(url)
            return r.text.strip()
        except: return json.dumps({"message": "AI Error", "operations": []})

def sanitize_content(path: str, content: str) -> str:
    path = path.lower()
    content = content.strip()
    
    # Remove Markdown wrappers
    content = re.sub(r'^```\w*\n', '', content)
    content = re.sub(r'\n```$', '', content)

    if path.endswith('.css'):
        content = re.sub(r'<style[^>]*>', '', content, flags=re.I)
        content = re.sub(r'</style>', '', content, flags=re.I)
        content = re.sub(r'<[^>]+>', '', content) 

    if path.endswith('.js') or path.endswith('.jsx'):
        content = re.sub(r'<script[^>]*>', '', content, flags=re.I)
        content = re.sub(r'</script>', '', content, flags=re.I)

    return content

def process_vfs(text: str, vfs: dict) -> tuple[str, dict, bool]:
    new_vfs = vfs.copy()
    match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
    if not match: match = re.search(r'(\{.*"operations":.*\})', text, re.DOTALL)
    
    updated = False
    msg = text
    
    if match:
        try:
            json_str = match.group(1).replace('\\n', '\\\\n')
            data = json.loads(json_str)
            msg = data.get("message", "Code updated.")
            
            for op in data.get("operations", []):
                path = op['path'].strip('/')
                clean_content = sanitize_content(path, op['content'])
                updated = True
                if op['action'] in ['create', 'update']: 
                    new_vfs[path] = clean_content
                elif op['action'] == 'delete' and path in new_vfs: 
                    del new_vfs[path]
        except Exception as e:
            logger.error(f"VFS Error: {e}")
            
    return msg, new_vfs, updated

def inject_assets(html: str, vfs: dict) -> str:
    """
    Injects CSS and JS into the HTML using lambda to avoid regex escape errors.
    """
    if not html: return "<h1>Error: Empty HTML</h1>"
    
    for path, code in vfs.items():
        name = path.split('/')[-1]
        
        # Safe replacement for CSS
        if path.endswith('.css'):
            pattern = f'<link[^>]*href=["\'].*?{re.escape(name)}["\'][^>]*>'
            # We use a lambda function for replacement to prevent 'bad escape' errors 
            # when the 'code' variable contains backslashes (e.g., \n, \s, etc.)
            html = re.sub(pattern, lambda m: f'<style>/*{path}*/\n{code}</style>', html, flags=re.I)
            
        # Safe replacement for JS
        if path.endswith('.js'):
            pattern = f'<script[^>]*src=["\'].*?{re.escape(name)}["\'][^>]*>.*?</script>'
            html = re.sub(pattern, lambda m: f'<script>/*{path}*/\n{code}</script>', html, flags=re.I|re.S)
            
    return html

# --- MASTER ENDPOINT ---
@router.post("/ask")
async def ask_ai(
    prompt: str = Form(...),
    tool_id: str = Form("god_mode"), 
    chat_id: Optional[str] = Form(None),
    files: List[UploadFile] = File(None),
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    chats = get_collection("chat_history")
    
    file_ctx = ""
    if files:
        for f in files: file_ctx += await parse_files(f)

    search_ctx = ""
    if any(t in prompt.lower() for t in ["search", "news", "latest", "price"]):
        search_ctx = perform_web_search(prompt)

    vfs = {}
    memory = ""
    if chat_id and ObjectId.is_valid(chat_id):
        c = chats.find_one({"_id": ObjectId(chat_id)})
        if c:
            vfs = c.get("vfs_state", {})
            memory = c.get("memory", "")

    # RELOAD PROMPT PER REQUEST
    current_sys_prompt = read_config_file("config/prompt.txt", GOD_MODE_PROMPT)

    sys_prompt = f"{current_sys_prompt}\nMEMORY: {memory}"
    sys_prompt += f"\nCURRENT FILES: {json.dumps(list(vfs.keys()))}"

    final = f"USER: {current_user['fullname']}\nFILES: {file_ctx}\nWEB: {search_ctx}\nQUERY: {prompt}"
    raw = await call_pollinations(final, sys_prompt)
    clean, vfs, updated = process_vfs(raw, vfs)

    msg = {"role": "ai", "content": clean, "ts": datetime.now(timezone.utc), "vfs_updated": updated}
    if chat_id and ObjectId.is_valid(chat_id):
        chats.update_one({"_id": ObjectId(chat_id)}, 
            {"$push": {"messages": {"role": "user", "content": prompt}}, "$set": {"vfs_state": vfs}})
        chats.update_one({"_id": ObjectId(chat_id)}, {"$push": {"messages": msg}})
        fid = chat_id
    else:
        r = chats.insert_one({"user_id": str(current_user["_id"]), "title": prompt[:30], "vfs_state": vfs, "memory": "", "messages": [msg]})
        fid = str(r.inserted_id)

    return {"status": "success", "chat_id": fid, "response": clean, "vfs": vfs, "data": msg}

# --- IMAGE GEN ---
@router.post("/generate-image")
async def generate_image(prompt: str = Form(...), current_user: Dict = Depends(auth_utils.get_current_user), chat_id: Optional[str] = Form(None)):
    flux_system = read_config_file("config/flux_enhance.txt", "Prompt Engineer")
    
    enhanced = await call_pollinations(f"Enhance for image: {prompt}", flux_system)
    url = f"https://flux-schnell.hello-kaiiddo.workers.dev/img?prompt={urllib.parse.quote(enhanced)}&t={int(time.time())}"
    try:
        async with httpx.AsyncClient() as c:
            r = await c.get(url)
            b64 = base64.b64encode(r.content).decode()
            data_uri = f"data:image/jpeg;base64,{b64}"
    except: raise HTTPException(503, "Flux Error")
    
    msg = {"role": "flux", "content": prompt, "image_data": data_uri, "ts": datetime.now()}
    if chat_id: get_collection("chat_history").update_one({"_id": ObjectId(chat_id)}, {"$push": {"messages": msg}})
    return {"status": "success", "image_url": data_uri}

# --- DEVOPS ---
@router.post("/publish/{chat_id}")
async def publish(chat_id: str, u: Dict = Depends(auth_utils.get_current_user)):
    c = get_collection("chat_history").find_one({"_id": ObjectId(chat_id)})
    if not c: raise HTTPException(404)
    did = secrets.token_urlsafe(6)
    get_collection("deployments").insert_one({"did": did, "vfs": c.get("vfs_state", {}), "uid": str(u["_id"])})
    return {"url": f"{BACKEND_URL}/ai/view/{did}"}

@router.get("/view/{did}")
async def view(did: str):
    d = get_collection("deployments").find_one({"did": did})
    if not d: return HTMLResponse("404", 404)
    vfs = d["vfs"]
    html = vfs.get("index.html", "<h1>No Index</h1>")
    return HTMLResponse(inject_assets(html, vfs))

@router.get("/live/{chat_id}")
async def live(chat_id: str):
    c = get_collection("chat_history").find_one({"_id": ObjectId(chat_id)})
    if not c: return HTMLResponse("404", 404)
    vfs = c.get("vfs_state", {})
    html = vfs.get("index.html", "<h1>Building...</h1>")
    
    # Basic Console Hijack for Parent Window Logging
    js = """<script>
    (function(){
        const s=window.parent.postMessage.bind(window.parent);
        console.log=(...a)=>s({type:'log',args:a},'*');
        console.error=(...a)=>s({type:'error',args:a},'*');
    })();</script>"""
    
    if "<head>" in html: html = html.replace("<head>", f"<head>{js}")
    else: html = js + html
    
    # Call the fixed inject_assets function
    try:
        final_html = inject_assets(html, vfs)
    except Exception as e:
        logger.error(f"Injection Error: {e}")
        final_html = html # Fallback to raw HTML if injection fails drastically

    return HTMLResponse(final_html)

# --- MEMORY & UTILS ---
@router.get("/chat/{chat_id}/memory")
async def get_memory(chat_id: str):
    c = get_collection("chat_history").find_one({"_id": ObjectId(chat_id)})
    return {"memory": c.get("memory", "")}

@router.post("/chat/{chat_id}/memory")
async def set_memory(chat_id: str, m: MemoryModel):
    get_collection("chat_history").update_one({"_id": ObjectId(chat_id)}, {"$set": {"memory": m.memory}})
    return {"status": "updated"}

@router.post("/run-code")
async def run_code(r: CodeRunRequest):
    v = "18.15.0" if r.language == "javascript" else "3.10.0"
    async with httpx.AsyncClient() as c:
        res = await c.post(PISTON_API, json={"language": r.language, "version": v, "files": [{"content": r.code}]})
        return res.json()

@router.post("/chats/new")
def new_c(u: Dict = Depends(auth_utils.get_current_user)):
    r = get_collection("chat_history").insert_one({"user_id": str(u["_id"]), "title": "New Project", "vfs_state": {}, "messages": []})
    return {"chat_id": str(r.inserted_id)}

@router.get("/chats")
def list_c(u: Dict = Depends(auth_utils.get_current_user)):
    c = get_collection("chat_history").find({"user_id": str(u["_id"])}).sort("_id", -1).limit(30)
    return [{"id": str(x["_id"]), "title": x.get("title", "Untitled")} for x in c]

@router.get("/chats/{chat_id}")
def get_c(chat_id: str):
    c = get_collection("chat_history").find_one({"_id": ObjectId(chat_id)})
    c["id"] = str(c["_id"]); del c["_id"]
    return c

@router.post("/api-key/generate")
async def gen_api_key(u: Dict = Depends(auth_utils.get_current_user)):
    key = f"sk_yuku_{secrets.token_hex(24)}"
    get_collection("users").update_one({"_id": u["_id"]}, {"$set": {"sdk_key": key}})
    return {"api_key": key}

@router.get("/health")
async def health():
    s = time.perf_counter()
    try: db.command("ping"); d="connected"
    except: d="disconnected"
    return {"status": "ok", "latency_us": int((time.perf_counter()-s)*1000000), "db": d}