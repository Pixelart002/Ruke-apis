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
from typing import Dict, List, Optional, Any, Union
from enum import Enum
from datetime import datetime, timezone
from pathlib import Path

# Image Processing for Context
from PIL import Image

import httpx
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel
from bson import ObjectId

# === IMPORTS ===
try:
    import pypdf
except ImportError:
    pypdf = None

from auth import utils as auth_utils 

# === DATABASE ===
try:
    from database import db
except ImportError:
    db = None
    logging.error("CRITICAL: database.py not found.")

# === CONFIGURATION ===
logger = logging.getLogger("AI_CORE_LEGACY")
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/ai", tags=["AI Core Legacy"])

# === CONSTANTS ===
FRONTEND_URL = "https://yuku-nine.vercel.app"
BACKEND_URL = "https://giant-noell-pixelart002-1c1d1fda.koyeb.app"

# === SYSTEM PROMPTS ===
VFS_SYSTEM_PROMPT = """
You are YUKU, an Advanced AI Coding Engine.
You are chatting with a user. You can generate code, images (via tools), or manage files.

RULES FOR CODE GENERATION (VFS):
1. If the user asks for a full application/website, you must use the Virtual File System (VFS).
2. Return a JSON object wrapped in ```json ... ```.
3. Structure:
```json
{
  "message": "I have created the login page.",
  "operations": [
    { "action": "create", "path": "index.html", "content": "..." },
    { "action": "update", "path": "style.css", "content": "..." }
  ]
}
```
4. If the user asks for a simple snippet, just provide the code block in the chat using standard markdown.
"""

# === HELPER FUNCTIONS ===

def get_db_collection(name: str):
    if db is None:
        raise HTTPException(500, "Database connection failed.")
    return db[name]

async def parse_uploaded_file(file: UploadFile) -> str:
    """Safe parsing of files for context (PDF, ZIP, Images)."""
    content_str = ""
    filename = file.filename.lower()
    
    try:
        file_bytes = await file.read()
        
        if filename.endswith(".pdf") and pypdf:
            try:
                reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                for page in reader.pages:
                    content_str += page.extract_text() + "\n"
            except: content_str += "[PDF Unreadable]"

        elif filename.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                for zname in z.namelist():
                    if not zname.endswith("/"):
                        with z.open(zname) as zf:
                            try:
                                content_str += f"\n--- FILE: {zname} ---\n{zf.read().decode('utf-8', errors='ignore')}"
                            except: pass

        elif filename.endswith(('.png', '.jpg', '.jpeg', '.webp')):
            # Free Vision Context (Metadata)
            try:
                img = Image.open(io.BytesIO(file_bytes))
                content_str += f"\n[IMAGE ATTACHMENT: {filename} | Size: {img.size} | Format: {img.format}]\n(Note: Visual pixel analysis unavailable in free mode. Use filename/metadata as context.)"
            except:
                content_str += f"[IMAGE ATTACHED: {filename}]"

        else:
            content_str = file_bytes.decode('utf-8', errors='ignore')
            
    except Exception as e:
        logger.error(f"File parse error: {e}")
        return f"[Error reading {filename}]"
        
    return f"\n=== CONTEXT FILE: {filename} ===\n{content_str}\n"

async def execute_pollinations_request(prompt: str, system_prompt: str) -> str:
    """Uses Pollinations.ai (Free/Unlimited)."""
    full_query = f"{system_prompt}\n\nUSER REQUEST: {prompt}\n\nASSISTANT RESPONSE:"
    encoded_prompt = urllib.parse.quote(full_query)
    seed = secrets.randbelow(99999)
    url = f"https://text.pollinations.ai/{encoded_prompt}?model=openai&seed={seed}"

    async with httpx.AsyncClient(timeout=100.0) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text.strip()
        except Exception as e:
            return json.dumps({"message": "AI Engine Connection Error.", "operations": []})

def process_vfs_logic(ai_response: str, current_vfs: Dict) -> tuple[str, Dict, bool]:
    """Detects JSON in response -> Updates VFS -> Returns (CleanText, Vfs, WasUpdated)."""
    updated_vfs = current_vfs.copy()
    clean_message = ai_response
    was_updated = False

    json_match = re.search(r'```json\s*(\{.*?\})\s*```', ai_response, re.DOTALL)
    if not json_match:
        json_match = re.search(r'(\{.*"operations":.*\})', ai_response, re.DOTALL)

    if json_match:
        try:
            data = json.loads(json_match.group(1))
            operations = data.get("operations", [])
            clean_message = data.get("message", "System updated files.")
            
            if operations:
                was_updated = True
                for op in operations:
                    action = op.get("action")
                    path = op.get("path")
                    content = op.get("content")
                    if action in ["create", "update"]:
                        updated_vfs[path] = content
                    elif action == "delete" and path in updated_vfs:
                        del updated_vfs[path]
        except: pass

    return clean_message, updated_vfs, was_updated

# === CORE ENDPOINTS ===

@router.post("/ask")
async def master_ai_handler(
    prompt: str = Form(...),
    tool_id: str = Form("mistral_default"),
    chat_id: Optional[str] = Form(None),
    files: List[UploadFile] = File(None),
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    chats = get_db_collection("chat_history")
    tools = get_db_collection("ai_tools")
    user_id = str(current_user["_id"])

    # 1. Parse Files
    file_context = ""
    if files:
        for file in files:
            file_context += await parse_uploaded_file(file)

    # 2. User Context Injection (from /me logic)
    user_context = f"USER CONTEXT: Name={current_user.get('fullname')}, Username={current_user.get('username')}, Email={current_user.get('email')}"
    
    full_prompt = f"{user_context}\n{file_context}\n\nQUERY: {prompt}"

    # 3. Load State
    vfs_state = {}
    chat_title = prompt[:30]
    if chat_id and ObjectId.is_valid(chat_id):
        chat = chats.find_one({"_id": ObjectId(chat_id)})
        if chat:
            vfs_state = chat.get("vfs_state", {})
            chat_title = chat.get("title", prompt[:30])

    # 4. System Prompt Logic
    # Allows user to customize via frontend, or uses default
    if tool_id == "code_editor" or "ide" in tool_id:
        file_list = list(vfs_state.keys())
        system_prompt = f"{VFS_SYSTEM_PROMPT}\n\nEXISTING FILES: {json.dumps(file_list)}"
        if "read" in prompt.lower() or "fix" in prompt.lower():
            system_prompt += f"\n\nFILE CONTENTS: {json.dumps(vfs_state)}"
    else:
        tool_db = tools.find_one({"slug": tool_id})
        system_prompt = tool_db["system_prompt"] if tool_db else VFS_SYSTEM_PROMPT

    # 5. Execution
    raw_response = await execute_pollinations_request(full_prompt, system_prompt)

    # 6. VFS Processing
    final_response, vfs_state, vfs_updated = process_vfs_logic(raw_response, vfs_state)

    # 7. Save
    msg = {
        "user_id": user_id, "tool": tool_id, "input": prompt, 
        "response": final_response, "timestamp": datetime.now(timezone.utc),
        "is_vfs_update": vfs_updated
    }

    if chat_id and ObjectId.is_valid(chat_id):
        chats.update_one(
            {"_id": ObjectId(chat_id)},
            {"$push": {"messages": msg}, "$set": {"vfs_state": vfs_state, "last_updated": datetime.now(timezone.utc)}}
        )
        final_chat_id = chat_id
    else:
        res = chats.insert_one({
            "user_id": user_id, "title": chat_title, "created_at": datetime.now(timezone.utc),
            "vfs_state": vfs_state, "messages": [msg]
        })
        final_chat_id = str(res.inserted_id)

    return {
        "status": "success", "chat_id": final_chat_id, 
        "data": msg, "vfs": vfs_state
    }

@router.post("/generate-image")
async def generate_image_handler(
    prompt: str = Form(...),
    current_user: Dict = Depends(auth_utils.get_current_user),
    chat_id: Optional[str] = Form(None)
):
    chats = get_db_collection("chat_history")
    user_id = str(current_user["_id"])

    # 1. Enhance
    enhanced = await execute_pollinations_request(f"Enhance for Flux: {prompt}", "You are a prompt engineer.")
    
    # 2. Generate
    ts = str(int(time.time()))
    url = f"https://flux-schnell.hello-kaiiddo.workers.dev/img?prompt={urllib.parse.quote(enhanced)}&t={ts}"
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url)
            b64 = base64.b64encode(resp.content).decode('utf-8')
            data_uri = f"data:image/jpeg;base64,{b64}"
    except: raise HTTPException(503, "Image gen failed")

    msg = {
        "user_id": user_id, "tool": "flux_image", "input": prompt,
        "image_data": data_uri, "timestamp": datetime.now(timezone.utc)
    }

    if chat_id and ObjectId.is_valid(chat_id):
        chats.update_one({"_id": ObjectId(chat_id)}, {"$push": {"messages": msg}})
        final_chat_id = chat_id
    else:
        res = chats.insert_one({"user_id": user_id, "title": "Image Gen", "messages": [msg]})
        final_chat_id = str(res.inserted_id)

    return {"status": "success", "chat_id": final_chat_id, "image_url": data_uri, "download_filename": f"gen_{ts}.jpg"}

# === CHAT MANAGEMENT (CRUD) ===

@router.post("/chats/new")
async def create_new_chat(current_user: Dict = Depends(auth_utils.get_current_user)):
    """Explicitly creates a new empty chat session."""
    res = get_db_collection("chat_history").insert_one({
        "user_id": str(current_user["_id"]),
        "title": "New Chat",
        "created_at": datetime.now(timezone.utc),
        "vfs_state": {},
        "messages": []
    })
    return {"status": "success", "chat_id": str(res.inserted_id)}

@router.get("/chats")
async def list_chats(current_user: Dict = Depends(auth_utils.get_current_user)):
    """Lists all chats for the sidebar drawer."""
    cursor = get_db_collection("chat_history").find(
        {"user_id": str(current_user["_id"])}
    ).sort("last_updated", -1).limit(50)
    
    chats = []
    for c in cursor:
        chats.append({
            "id": str(c["_id"]),
            "title": c.get("title", "Untitled Chat"),
            "date": c.get("created_at")
        })
    return chats

@router.get("/chats/{chat_id}")
async def get_chat_data(chat_id: str, current_user: Dict = Depends(auth_utils.get_current_user)):
    """Loads a specific chat."""
    chat = get_db_collection("chat_history").find_one({
        "_id": ObjectId(chat_id), 
        "user_id": str(current_user["_id"])
    })
    if not chat: raise HTTPException(404, "Chat not found")
    
    # Convert ObjectIds to strings for JSON serialization
    chat["id"] = str(chat["_id"])
    del chat["_id"]
    return chat

# === TOOLS & UTILS ===

@router.post("/tools/add")
async def add_tool(name: str, slug: str, system_prompt: str, tool_type: str):
    get_db_collection("ai_tools").update_one(
        {"slug": slug}, 
        {"$set": {"name": name, "slug": slug, "system_prompt": system_prompt, "type": tool_type}}, 
        upsert=True
    )
    return {"status": "ok"}

@router.post("/share/{chat_id}")
async def share_chat(chat_id: str, current_user: Dict = Depends(auth_utils.get_current_user)):
    token = secrets.token_urlsafe(16)
    get_db_collection("chat_history").update_one(
        {"_id": ObjectId(chat_id), "user_id": str(current_user["_id"])},
        {"$set": {"share_token": token, "is_public": True}}
    )
    return {"share_url": f"{FRONTEND_URL}/share/{token}"}

@router.post("/api-key/generate")
async def generate_sdk_key(current_user: Dict = Depends(auth_utils.get_current_user)):
    key = f"sk_yuku_{secrets.token_hex(16)}"
    get_db_collection("users").update_one({"_id": current_user["_id"]}, {"$set": {"sdk_api_key": key}})
    return {"api_key": key}

@router.get("/health")
async def health():
    s = time.perf_counter()
    try: db.command("ping"); d="ok"
    except: d="err"
    lat = (time.perf_counter() - s) * 1_000_000
    return {"status": "ok", "latency_us": int(lat), "db": d, "mode": "legacy_god"}