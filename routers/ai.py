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

import httpx
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel
from bson import ObjectId

# === LIBRARIES ===
try:
    import pypdf
except ImportError:
    pypdf = None

# For Image Metadata (Prevent 503)
from PIL import Image

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

# === SYSTEM PROMPTS ===
# Base Prompt
BASE_SYSTEM_PROMPT = """
You are YUKU, an advanced AI Engine. 
Context: User is {fullname} (ID: {userid}).

MODES:
1. CHAT: Answer questions. If code is requested, provide snippets.
2. CODE_EDITOR: If the user wants a full project/website, output JSON for the VFS (Virtual File System).
3. IMAGE: If the user asks to generate an image, guide them to use the Image Tool.
"""

# VFS Specific Prompt
VFS_INSTRUCTIONS = """
You are in IDE MODE. You control a Virtual File System.
Rules:
1. Return a JSON object wrapped in ```json ... ```.
2. JSON Format:
{
  "message": "Brief status update.",
  "operations": [
    { "action": "create", "path": "index.html", "content": "..." },
    { "action": "update", "path": "style.css", "content": "..." },
    { "action": "delete", "path": "old.js" }
  ]
}
3. Always include 'index.html' for web projects.
"""

# === HELPER FUNCTIONS ===

def get_db_collection(name: str):
    if db is None:
        raise HTTPException(500, "Database connection failed.")
    return db[name]

async def parse_uploaded_file(file: UploadFile) -> str:
    """
    Parses context from files. Fixes 503 Error by safely handling images.
    """
    content_str = ""
    filename = file.filename.lower()
    
    try:
        file_bytes = await file.read()
        
        # 1. PDF
        if filename.endswith(".pdf") and pypdf:
            try:
                reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                for page in reader.pages:
                    content_str += page.extract_text() + "\n"
            except:
                content_str += "[PDF Content Unreadable]\n"

        # 2. ZIP
        elif filename.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                for zname in z.namelist():
                    if not zname.endswith("/"):
                        with z.open(zname) as zf:
                            try:
                                content_str += f"\n--- FILE: {zname} ---\n{zf.read().decode('utf-8', errors='ignore')}"
                            except: pass

        # 3. IMAGE (Context Only - No Key Required)
        elif filename.endswith(('.png', '.jpg', '.jpeg', '.webp')):
            try:
                img = Image.open(io.BytesIO(file_bytes))
                content_str += f"\n[IMAGE META: {filename} | Size: {img.size} | Format: {img.format}]\n(Note: I can see this file exists. I cannot read pixels directly without a Vision Key, but I can use the filename as context.)"
            except:
                content_str += f"\n[IMAGE ATTACHED: {filename}]"

        # 4. TEXT
        else:
            content_str = file_bytes.decode('utf-8', errors='ignore')
            
    except Exception as e:
        logger.error(f"File parse error: {e}")
        return f"[Error reading file {filename}]"
        
    return f"\n=== CONTEXT FILE: {filename} ===\n{content_str}\n"

async def execute_pollinations_request(prompt: str, system_prompt: str) -> str:
    """
    Uses Pollinations.ai (OpenAI Model) - Free, Unlimited, Stable.
    """
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
            logger.error(f"Pollinations API Error: {e}")
            return json.dumps({
                "message": "Error connecting to AI Engine. Please try again.",
                "operations": []
            })

def process_vfs_logic(ai_response: str, current_vfs: Dict) -> tuple[str, Dict]:
    """
    Detects JSON in AI response and updates the Virtual File System.
    """
    updated_vfs = current_vfs.copy()
    clean_message = ai_response

    # Regex to find JSON block inside ```json ... ```
    json_match = re.search(r'```json\s*(\{.*?\})\s*```', ai_response, re.DOTALL)
    
    if not json_match:
        json_match = re.search(r'(\{.*"operations":.*\})', ai_response, re.DOTALL)

    if json_match:
        try:
            json_str = json_match.group(1)
            data = json.loads(json_str)
            
            operations = data.get("operations", [])
            clean_message = data.get("message", "Project updated successfully.")

            for op in operations:
                action = op.get("action")
                path = op.get("path")
                content = op.get("content")

                if action == "create" or action == "update":
                    updated_vfs[path] = content
                elif action == "delete" and path in updated_vfs:
                    del updated_vfs[path]
                    
        except json.JSONDecodeError:
            pass 

    return clean_message, updated_vfs

# === CORE ENDPOINTS ===

@router.post("/ask")
async def master_ai_handler(
    prompt: str = Form(...),
    tool_id: str = Form("mistral_default"),
    chat_id: Optional[str] = Form(None),
    custom_system_prompt: Optional[str] = Form(None),
    files: List[UploadFile] = File(None),
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    chats = get_db_collection("chat_history")
    tools = get_db_collection("ai_tools")
    
    user_id = str(current_user["_id"])
    fullname = current_user.get("fullname", "User")

    # 1. Parse Files
    file_context = ""
    if files:
        for file in files:
            file_context += await parse_uploaded_file(file)

    full_prompt = f"{file_context}\n\n{prompt}"

    # 2. Load State
    vfs_state = {}
    if chat_id and ObjectId.is_valid(chat_id):
        chat = chats.find_one({"_id": ObjectId(chat_id)})
        if chat:
            vfs_state = chat.get("vfs_state", {})

    # 3. Determine Instructions
    # Priority: Custom -> Code Mode -> Tool DB -> Default
    if custom_system_prompt:
         system_prompt = custom_system_prompt
    elif tool_id == "code_editor":
        file_list = list(vfs_state.keys())
        system_prompt = f"{VFS_INSTRUCTIONS}\n\nEXISTING FILES: {json.dumps(file_list)}"
        if "read" in prompt.lower() or "fix" in prompt.lower():
             system_prompt += f"\n\nFILE CONTEXT: {json.dumps(vfs_state)}"
    else:
        tool_db = tools.find_one({"slug": tool_id})
        base = BASE_SYSTEM_PROMPT.format(fullname=fullname, userid=user_id)
        system_prompt = tool_db["system_prompt"] if tool_db else base

    # 4. Execute AI
    raw_response = await execute_pollinations_request(full_prompt, system_prompt)

    # 5. Process VFS
    final_response, vfs_state = process_vfs_logic(raw_response, vfs_state)

    # 6. Save
    msg_payload = {
        "user_id": user_id,
        "tool": tool_id,
        "input": prompt,
        "response": final_response,
        "timestamp": datetime.now(timezone.utc)
    }

    if chat_id and ObjectId.is_valid(chat_id):
        chats.update_one(
            {"_id": ObjectId(chat_id)},
            {
                "$push": {"messages": msg_payload},
                "$set": {"vfs_state": vfs_state, "last_updated": datetime.now(timezone.utc)}
            }
        )
        final_chat_id = chat_id
    else:
        new_chat = {
            "user_id": user_id,
            "title": prompt[:30],
            "created_at": datetime.now(timezone.utc),
            "vfs_state": vfs_state,
            "is_public": False,
            "messages": [msg_payload]
        }
        res = chats.insert_one(new_chat)
        final_chat_id = str(res.inserted_id)

    return {
        "status": "success",
        "chat_id": final_chat_id,
        "data": msg_payload,
        "vfs": vfs_state
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
    enhanced = await execute_pollinations_request(f"Enhance this for Flux Photo: {prompt}", "You are a prompt engineer.")
    
    # 2. Generate
    ts = str(int(time.time()))
    url = f"https://flux-schnell.hello-kaiiddo.workers.dev/img?prompt={urllib.parse.quote(enhanced)}&t={ts}"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=90.0)
            resp.raise_for_status()
            b64 = base64.b64encode(resp.content).decode('utf-8')
            data_uri = f"data:image/jpeg;base64,{b64}"
    except Exception:
        raise HTTPException(503, "Image service unavailable.")

    # 3. Save
    payload = {
        "user_id": user_id, "tool": "flux_image", "input": prompt,
        "image_data": data_uri, "timestamp": datetime.now(timezone.utc)
    }

    if chat_id and ObjectId.is_valid(chat_id):
        chats.update_one({"_id": ObjectId(chat_id)}, {"$push": {"messages": payload}})
        final_chat_id = chat_id
    else:
        res = chats.insert_one({"user_id": user_id, "title": "Image Gen", "messages": [payload]})
        final_chat_id = str(res.inserted_id)

    return {"status": "success", "chat_id": final_chat_id, "image_url": data_uri, "download_filename": f"yuku_{ts}.jpg"}

# === UTILS / SHARE / SDK ===

@router.get("/health")
async def health_check():
    s = time.perf_counter()
    try: db.command("ping"); dbs="connected"
    except: dbs="disconnected"
    e = time.perf_counter()
    return {"status": "active", "latency_us": int((e-s)*1_000_000), "db": dbs}

@router.post("/tools/add")
async def add_tool(name: str, slug: str, system_prompt: str, tool_type: str):
    get_db_collection("ai_tools").update_one(
        {"slug": slug}, 
        {"$set": {"name": name, "slug": slug, "system_prompt": system_prompt, "type": tool_type}}, 
        upsert=True
    )
    return {"status": "ok"}

@router.post("/share/{chat_id}")
async def create_share_link(chat_id: str, current_user: Dict = Depends(auth_utils.get_current_user)):
    chats = get_db_collection("chat_history")
    token = secrets.token_urlsafe(16)
    chats.update_one({"_id": ObjectId(chat_id), "user_id": str(current_user["_id"])}, {"$set": {"share_token": token, "is_public": True}})
    return {"share_url": f"{FRONTEND_URL}/share/{token}"}

@router.post("/api-key/generate")
async def generate_api_key(current_user: Dict = Depends(auth_utils.get_current_user)):
    api_key = f"sk_{secrets.token_hex(24)}"
    get_db_collection("users").update_one({"_id": current_user["_id"]}, {"$set": {"sdk_api_key": api_key}})
    return {"api_key": api_key}