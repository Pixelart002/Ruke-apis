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
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

# --- LIBRARIES ---
from PIL import Image
import httpx
# [FIX] Switched to DDGS (Stable) to fix ImportError: cannot import name 'AsyncDDGS'
from duckduckgo_search import DDGS 
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Body
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

# --- SYSTEM PROMPTS ---
VFS_PROMPT = """
You are YUKU, an Expert AI DevOps Architect.
You have a Virtual File System (VFS). You MUST organize code into FOLDERS.

RULES:
1. Return JSON wrapped in ```json ... ```.
2. Format: { "message": "...", "operations": [ { "action": "create", "path": "src/components/Nav.js", "content": "..." } ] }
3. USE RELATIVE PATHS. 
4. ALWAYS include 'index.html' in the root.
5. Design: Modern, Dark Mode, Emerald Accents (v0 style).
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

# --- HELPERS ---
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
            content += f"\n[IMAGE: {fname} | {img.size}]\n"
        else: content = data.decode('utf-8', errors='ignore')
    except: return f"[Error reading {fname}]"
    return f"\n=== FILE: {fname} ===\n{content}\n"

# [FIXED] Using Synchronous DDGS which is compatible with all versions
async def web_search(query: str) -> str:
    try:
        # Use context manager to handle session correctly
        with DDGS() as ddgs:
            # .text() returns a generator/list, we convert to list to check content
            results = list(ddgs.text(query, max_results=3))
            if not results: return ""
            
            summary = "\n[WEB DATA]:\n"
            for r in results: 
                summary += f"- {r['title']}: {r['body']}\n"
            return summary
    except Exception as e:
        # Log error but don't crash
        print(f"Search Error: {e}") 
        return ""

async def call_ai(prompt: str, system: str) -> str:
    full = f"{system}\n\nUSER: {prompt}\n\nASSISTANT:"
    url = f"https://text.pollinations.ai/{urllib.parse.quote(full)}?model=openai&seed={secrets.randbelow(9999)}"
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            r = await client.get(url)
            return r.text.strip()
        except: return json.dumps({"message": "AI Error", "operations": []})

def process_vfs(text: str, vfs: dict) -> tuple[str, dict, bool]:
    new_vfs = vfs.copy()
    match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
    if not match: match = re.search(r'(\{.*"operations":.*\})', text, re.DOTALL)
    
    updated = False
    msg = text
    
    if match:
        try:
            data = json.loads(match.group(1))
            msg = data.get("message", "Code updated.")
            for op in data.get("operations", []):
                updated = True
                path = op['path'].strip('/')
                if op['action'] in ['create', 'update']: new_vfs[path] = op['content']
                elif op['action'] == 'delete' and path in new_vfs: del new_vfs[path]
        except: pass
    return msg, new_vfs, updated

def inject_assets(html: str, vfs: dict) -> str:
    # Smart Linking for Folders
    for path, code in vfs.items():
        name = path.split('/')[-1]
        if path.endswith('.css'):
            html = re.sub(f'<link[^>]*href=["\'].*?{re.escape(name)}["\'][^>]*>', f'<style>/*{path}*/\n{code}</style>', html, flags=re.I)
        if path.endswith('.js'):
            html = re.sub(f'<script[^>]*src=["\'].*?{re.escape(name)}["\'][^>]*>.*?</script>', f'<script>/*{path}*/\n{code}</script>', html, flags=re.I|re.S)
    return html

# --- MASTER ENDPOINT ---
@router.post("/ask")
async def ask_ai(
    prompt: str = Form(...),
    tool_id: str = Form("mistral_default"),
    chat_id: Optional[str] = Form(None),
    files: List[UploadFile] = File(None),
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    chats = get_collection("chat_history")
    
    # 1. Parse Files
    file_ctx = ""
    if files:
        for f in files: file_ctx += await parse_files(f)

    # 2. Search
    search_ctx = ""
    if any(t in prompt.lower() for t in ["search", "news", "latest", "price"]):
        search_ctx = await web_search(prompt)

    # 3. Load State & Memory
    vfs = {}
    memory = ""
    if chat_id and ObjectId.is_valid(chat_id):
        c = chats.find_one({"_id": ObjectId(chat_id)})
        if c:
            vfs = c.get("vfs_state", {})
            memory = c.get("memory", "")

    # 4. System Prompt
    agent = get_collection("ai_agents").find_one({"slug": tool_id})
    sys_prompt = agent["system_prompt"] if agent else VFS_PROMPT
    sys_prompt += f"\nMEMORY: {memory}"
    
    if "code" in tool_id or "ide" in tool_id:
        sys_prompt += f"\nCURRENT FILES: {json.dumps(list(vfs.keys()))}"

    # 5. Execute
    final = f"USER: {current_user['fullname']}\nFILES: {file_ctx}\nWEB: {search_ctx}\nQUERY: {prompt}"
    raw = await call_ai(final, sys_prompt)
    clean, vfs, updated = process_vfs(raw, vfs)

    # 6. Save
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

# --- IMAGE GENERATION ---
@router.post("/generate-image")
async def generate_image(prompt: str = Form(...), current_user: Dict = Depends(auth_utils.get_current_user), chat_id: str = Form(None)):
    enhanced = await call_ai(f"Enhance: {prompt}", "Prompt Engineer")
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

# --- AGENT REGISTRY (New!) ---
@router.post("/agents/register")
async def register_agent(agent: AgentModel, u: Dict = Depends(auth_utils.get_current_user)):
    get_collection("ai_agents").update_one({"slug": agent.slug}, {"$set": agent.dict()}, upsert=True)
    return {"status": "registered", "slug": agent.slug}

@router.get("/agents")
async def list_agents():
    return list(get_collection("ai_agents").find({}, {"_id": 0}))

@router.get("/agent/{slug}")
async def get_agent(slug: str):
    return get_collection("ai_agents").find_one({"slug": slug}, {"_id": 0}) or {}

# --- MEMORY MANAGEMENT ---
@router.get("/chat/{chat_id}/memory")
async def get_memory(chat_id: str):
    c = get_collection("chat_history").find_one({"_id": ObjectId(chat_id)})
    return {"memory": c.get("memory", "")}

@router.post("/chat/{chat_id}/memory")
async def set_memory(chat_id: str, m: MemoryModel):
    get_collection("chat_history").update_one({"_id": ObjectId(chat_id)}, {"$set": {"memory": m.memory}})
    return {"status": "updated"}

# --- SDK & API KEYS ---
@router.post("/api-key/generate")
async def gen_api_key(u: Dict = Depends(auth_utils.get_current_user)):
    key = f"sk_yuku_{secrets.token_hex(24)}"
    get_collection("users").update_one({"_id": u["_id"]}, {"$set": {"sdk_key": key}})
    return {"api_key": key}

@router.get("/api-key")
async def get_api_key(u: Dict = Depends(auth_utils.get_current_user)):
    return {"api_key": u.get("sdk_key", "No key generated")}

# --- DEVOPS: PUBLISH & LIVE ---
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
    # Console Injection
    js = """<script>
    (function(){
        const s=window.parent.postMessage.bind(window.parent);
        console.log=(...a)=>s({type:'log',args:a},'*');
        console.error=(...a)=>s({type:'error',args:a},'*');
    })();</script>"""
    if "<head>" in html: html = html.replace("<head>", f"<head>{js}")
    else: html = js + html
    return HTMLResponse(inject_assets(html, vfs))

# --- UTILS ---
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

@router.get("/health")
async def health():
    s = time.perf_counter()
    try: db.command("ping"); d="connected"
    except: d="disconnected"
    return {"status": "ok", "latency_us": int((time.perf_counter()-s)*1000000), "db": d}