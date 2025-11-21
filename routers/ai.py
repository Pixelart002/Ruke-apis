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

# Image Processing
from PIL import Image

import httpx
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Body
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel
from bson import ObjectId

# === OPTIONAL IMPORTS ===
try:
    import pypdf
except ImportError:
    pypdf = None

from auth import utils as auth_utils 
from database import db

# === CONFIGURATION ===
logger = logging.getLogger("AI_CORE_LEGACY")
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/ai", tags=["AI Core Legacy"])

# === CONSTANTS ===
FRONTEND_URL = "https://yuku-nine.vercel.app"
PISTON_API_URL = "https://emkc.org/api/v2/piston/execute"

# === SYSTEM PROMPTS ===
VFS_SYSTEM_PROMPT = """
You are YUKU, an Advanced AI Coding Engine & Architect.
You have access to a Virtual File System (VFS) and Real-Time Web Search.

RULES:
1. If asked for code/apps, return JSON wrapped in ```json ... ``` blocks.
2. Structure: { "message": "...", "operations": [ { "action": "create", "path": "index.html", "content": "..." } ] }
3. If asked for diagrams, use Mermaid.js syntax wrapped in ```mermaid ... ```.
4. Always include index.html for web projects.
"""

# === MODELS ===
class AgentRegister(BaseModel):
    name: str
    slug: str
    system_prompt: str
    description: str = "Custom Agent"

class MemoryUpdate(BaseModel):
    memory: str

class CodeRunRequest(BaseModel):
    language: str
    code: str

# === HELPER FUNCTIONS ===

def get_collection(name: str):
    if db is None: raise HTTPException(500, "DB Connection Failed")
    return db[name]

async def parse_file_context(file: UploadFile) -> str:
    """ Robust file parsing to prevent 503s. """
    content = ""
    fname = file.filename.lower()
    try:
        data = await file.read()
        if fname.endswith(".pdf") and pypdf:
            try:
                reader = pypdf.PdfReader(io.BytesIO(data))
                for p in reader.pages: content += p.extract_text() + "\n"
            except: content += "[PDF Unreadable]"
        elif fname.endswith(('.png', '.jpg', '.jpeg', '.webp')):
            try:
                img = Image.open(io.BytesIO(data))
                content += f"\n[IMAGE: {fname} | {img.size} | {img.format}]\n(Client-side OCR will provide text content)"
            except: content += f"[IMAGE: {fname}]"
        else:
            content = data.decode('utf-8', errors='ignore')
    except Exception as e:
        logger.error(f"Parse Error: {e}")
        return f"[Error reading {fname}]"
    return f"\n=== FILE: {fname} ===\n{content}\n"

async def call_pollinations(prompt: str, system: str) -> str:
    """ Unlimited Free AI Generation """
    full_text = f"{system}\n\nUSER: {prompt}\n\nASSISTANT:"
    encoded = urllib.parse.quote(full_text)
    seed = secrets.randbelow(999999)
    url = f"https://text.pollinations.ai/{encoded}?model=openai&seed={seed}"
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text.strip()
        except Exception as e:
            return json.dumps({"message": f"AI Error: {str(e)}", "operations": []})

def process_vfs(response_text: str, current_vfs: Dict) -> tuple[str, Dict, bool]:
    """ Extracts VFS JSON from AI response """
    vfs = current_vfs.copy()
    msg = response_text
    updated = False
    
    match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
    if not match: match = re.search(r'(\{.*"operations":.*\})', response_text, re.DOTALL)
    
    if match:
        try:
            data = json.loads(match.group(1))
            msg = data.get("message", "Code updated.")
            for op in data.get("operations", []):
                updated = True
                if op['action'] in ['create', 'update']: vfs[op['path']] = op['content']
                elif op['action'] == 'delete' and op['path'] in vfs: del vfs[op['path']]
        except: pass
        
    return msg, vfs, updated

# === ENDPOINTS: CHAT & VFS ===

@router.post("/ask")
async def ask_ai(
    prompt: str = Form(...),
    tool_id: str = Form("mistral_default"),
    chat_id: Optional[str] = Form(None),
    files: List[UploadFile] = File(None),
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    chats = get_collection("chat_history")
    user_id = str(current_user["_id"])
    
    # 1. Context Building
    file_ctx = ""
    if files:
        for f in files: file_ctx += await parse_file_context(f)
    
    user_ctx = f"USER: {current_user.get('fullname')} ({current_user.get('email')})"
    
    # 2. Load Chat State
    vfs = {}
    chat_memory = ""
    title = prompt[:30]
    
    if chat_id and ObjectId.is_valid(chat_id):
        chat = chats.find_one({"_id": ObjectId(chat_id)})
        if chat:
            vfs = chat.get("vfs_state", {})
            chat_memory = chat.get("memory", "")
            title = chat.get("title", title)

    # 3. System Prompt Selection
    tools = get_collection("ai_agents") # Using agents collection for tools
    agent = tools.find_one({"slug": tool_id})
    
    base_system = agent["system_prompt"] if agent else VFS_SYSTEM_PROMPT
    
    # Inject Dynamic Context
    system_prompt = f"{base_system}\n\n{user_ctx}\nMEMORY: {chat_memory}"
    if "code" in tool_id or "ide" in tool_id:
        system_prompt += f"\nCURRENT FILES: {json.dumps(list(vfs.keys()))}"
        if "read" in prompt.lower() or "fix" in prompt.lower():
            system_prompt += f"\nFILE CONTENT: {json.dumps(vfs)}"

    # 4. Execution
    final_prompt = f"{file_ctx}\n\nQUERY: {prompt}"
    raw_res = await call_pollinations(final_prompt, system_prompt)
    
    # 5. VFS Processing
    clean_res, vfs, is_updated = process_vfs(raw_res, vfs)
    
    # 6. Save
    msg = {
        "role": "ai", "content": clean_res, "timestamp": datetime.now(timezone.utc),
        "vfs_updated": is_updated
    }
    
    if chat_id and ObjectId.is_valid(chat_id):
        chats.update_one(
            {"_id": ObjectId(chat_id)},
            {"$push": {"messages": {"role": "user", "content": prompt, "timestamp": datetime.now(timezone.utc)}},
             "$set": {"vfs_state": vfs, "last_updated": datetime.now(timezone.utc)}}
        )
        chats.update_one({"_id": ObjectId(chat_id)}, {"$push": {"messages": msg}})
        final_id = chat_id
    else:
        res = chats.insert_one({
            "user_id": user_id, "title": title, "created_at": datetime.now(timezone.utc),
            "vfs_state": vfs, "memory": "", "messages": [
                {"role": "user", "content": prompt, "timestamp": datetime.now(timezone.utc)}, msg
            ]
        })
        final_id = str(res.inserted_id)

    return {"status": "success", "chat_id": final_id, "response": clean_res, "vfs": vfs}

# === ENDPOINTS: IMAGE GENERATION ===

@router.post("/generate-image")
async def generate_image(
    prompt: str = Form(...),
    current_user: Dict = Depends(auth_utils.get_current_user),
    chat_id: Optional[str] = Form(None)
):
    enhanced = await call_pollinations(f"Enhance for Flux: {prompt}", "You are a prompt engineer.")
    ts = str(int(time.time()))
    url = f"https://flux-schnell.hello-kaiiddo.workers.dev/img?prompt={urllib.parse.quote(enhanced)}&t={ts}"
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url)
            b64 = base64.b64encode(resp.content).decode('utf-8')
            data_uri = f"data:image/jpeg;base64,{b64}"
    except: raise HTTPException(503, "Flux Service Unavailable")

    msg = {"role": "flux", "content": prompt, "image": data_uri, "timestamp": datetime.now(timezone.utc)}
    
    if chat_id and ObjectId.is_valid(chat_id):
        get_collection("chat_history").update_one({"_id": ObjectId(chat_id)}, {"$push": {"messages": msg}})
        final_id = chat_id
    else:
        res = get_collection("chat_history").insert_one({
            "user_id": str(current_user["_id"]), "title": "Image Gen", "messages": [msg]
        })
        final_id = str(res.inserted_id)

    return {"status": "success", "chat_id": final_id, "image_url": data_uri}

# === ENDPOINTS: CHAT MANAGEMENT & MEMORY ===

@router.post("/chats/new")
async def create_chat(current_user: Dict = Depends(auth_utils.get_current_user)):
    res = get_collection("chat_history").insert_one({
        "user_id": str(current_user["_id"]),
        "title": "New Session",
        "created_at": datetime.now(timezone.utc),
        "vfs_state": {},
        "memory": "",
        "messages": []
    })
    return {"chat_id": str(res.inserted_id)}

@router.get("/chats")
async def list_chats(current_user: Dict = Depends(auth_utils.get_current_user)):
    cursor = get_collection("chat_history").find(
        {"user_id": str(current_user["_id"])}
    ).sort("last_updated", -1).limit(50)
    return [{"id": str(c["_id"]), "title": c.get("title", "Untitled")} for c in cursor]

@router.get("/chats/{chat_id}")
async def get_chat(chat_id: str, current_user: Dict = Depends(auth_utils.get_current_user)):
    chat = get_collection("chat_history").find_one({"_id": ObjectId(chat_id), "user_id": str(current_user["_id"])})
    if not chat: raise HTTPException(404, "Not Found")
    chat["id"] = str(chat["_id"])
    del chat["_id"]
    return chat

@router.get("/chat/{chat_id}/memory")
async def get_chat_memory(chat_id: str, current_user: Dict = Depends(auth_utils.get_current_user)):
    chat = get_collection("chat_history").find_one({"_id": ObjectId(chat_id)}, {"memory": 1})
    return {"memory": chat.get("memory", "")}

@router.post("/chat/{chat_id}/memory")
async def update_chat_memory(chat_id: str, update: MemoryUpdate, current_user: Dict = Depends(auth_utils.get_current_user)):
    get_collection("chat_history").update_one({"_id": ObjectId(chat_id)}, {"$set": {"memory": update.memory}})
    return {"status": "updated"}

# === ENDPOINTS: AGENT MANAGEMENT ===

@router.post("/agents/register")
async def register_agent(agent: AgentRegister, current_user: Dict = Depends(auth_utils.get_current_user)):
    get_collection("ai_agents").update_one(
        {"slug": agent.slug},
        {"$set": agent.dict()},
        upsert=True
    )
    return {"status": "registered", "slug": agent.slug}

@router.get("/agents")
async def list_agents():
    cursor = get_collection("ai_agents").find({}, {"name": 1, "slug": 1, "description": 1, "_id": 0})
    return list(cursor)

@router.get("/agent/{agent_slug}")
async def get_agent(agent_slug: str):
    agent = get_collection("ai_agents").find_one({"slug": agent_slug}, {"_id": 0})
    if not agent: raise HTTPException(404, "Agent not found")
    return agent

# === ENDPOINTS: TOOLS & UTILS ===

@router.post("/share-link/{chat_id}")
async def share_chat(chat_id: str, current_user: Dict = Depends(auth_utils.get_current_user)):
    token = secrets.token_urlsafe(12)
    get_collection("chat_history").update_one(
        {"_id": ObjectId(chat_id)}, {"$set": {"share_token": token, "is_public": True}}
    )
    return {"link": f"{FRONTEND_URL}/share/{token}"}

@router.post("/run-code")
async def run_code_piston(req: CodeRunRequest, current_user: Dict = Depends(auth_utils.get_current_user)):
    """ Secure execution via Piston API """
    lang_map = {"python": "3.10.0", "javascript": "18.15.0"}
    version = lang_map.get(req.language, "3.10.0")
    
    async with httpx.AsyncClient() as client:
        res = await client.post(PISTON_API_URL, json={
            "language": req.language, "version": version,
            "files": [{"content": req.code}]
        })
        return res.json()

@router.get("/live/{chat_id}")
async def live_hosting(chat_id: str):
    """ Hosts the VFS as a real website """
    chat = get_collection("chat_history").find_one({"_id": ObjectId(chat_id)})
    if not chat: return HTMLResponse("Project Not Found", 404)
    vfs = chat.get("vfs_state", {})
    html = vfs.get("index.html", "<h1>No index.html</h1>")
    if "style.css" in vfs: html = html.replace("</head>", f"<style>{vfs['style.css']}</style></head>")
    if "script.js" in vfs: html = html.replace("</body>", f"<script>{vfs['script.js']}</script></body>")
    return HTMLResponse(html)

@router.get("/download-project/{chat_id}")
async def download_project(chat_id: str):
    chat = get_collection("chat_history").find_one({"_id": ObjectId(chat_id)})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for k, v in chat.get("vfs_state", {}).items(): z.writestr(k, v)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip", headers={"Content-Disposition": f"attachment; filename=project_{chat_id}.zip"})

@router.post("/api-key/generate")
async def generate_key(current_user: Dict = Depends(auth_utils.get_current_user)):
    key = f"sk_yuku_{secrets.token_hex(16)}"
    get_collection("users").update_one({"_id": current_user["_id"]}, {"$set": {"api_key": key}})
    return {"key": key}

@router.get("/health")
async def health():
    s = time.perf_counter()
    try: db.command("ping"); d="connected"
    except: d="disconnected"
    return {"status": "ok", "latency_us": int((time.perf_counter()-s)*1000000), "db": d}