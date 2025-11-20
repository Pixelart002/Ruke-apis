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

import httpx
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel
from bson import ObjectId

# === LIBRARIES ===
try:
    import pypdf
except ImportError:
    pypdf = None

# Free Vision Placeholder (PIL)
try:
    from PIL import Image
except ImportError:
    Image = None

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

# === SYSTEM PROMPTS & INSTRUCTIONS ===
VFS_SYSTEM_PROMPT = """
You are YUKU, an advanced AI Coding Engine with direct control over a Virtual File System (VFS).

INSTRUCTIONS:
1. If the user asks for code/websites, DO NOT just print code. You MUST return a JSON object.
2. Structure:
```json
{
  "message": "I have created the portfolio page.",
  "operations": [
    { "action": "create", "path": "index.html", "content": "..." },
    { "action": "update", "path": "style.css", "content": "..." }
  ],
  "open_ide": true
}
```
3. Valid actions: "create", "update", "delete".
4. If the user asks for an image, return: { "command": "generate_image", "prompt": "..." }
5. If you need an external API key, return: { "ui_request": "api_key_input", "service": "openai" }
"""

# === HELPER FUNCTIONS ===

def get_db_collection(name: str):
    if db is None:
        raise HTTPException(500, "Database connection failed.")
    return db[name]

async def parse_uploaded_file(file: UploadFile) -> str:
    """
    Parses context from files. Handles Images safely to prevent 503 errors.
    """
    content_str = ""
    filename = file.filename.lower()
    
    try:
        file_bytes = await file.read()
        
        # 1. PDF Parsing
        if filename.endswith(".pdf") and pypdf:
            try:
                reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                for page in reader.pages:
                    content_str += page.extract_text() + "\n"
            except:
                content_str += "[PDF Content Unreadable]\n"

        # 2. Zip Parsing
        elif filename.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                for zname in z.namelist():
                    if not zname.endswith("/"):
                        with z.open(zname) as zf:
                            try:
                                content_str += f"\n--- FILE: {zname} ---\n{zf.read().decode('utf-8', errors='ignore')}"
                            except: pass

        # 3. Image Handling (Safe Mode)
        elif filename.endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
            if Image:
                try:
                    img = Image.open(io.BytesIO(file_bytes))
                    content_str += f"\n[IMAGE CONTEXT: {filename} | Size: {img.size} | Format: {img.format}]\n(Visual analysis limited in Legacy Mode)"
                except:
                    content_str += f"\n[IMAGE UPLOADED: {filename}]"
            else:
                content_str += f"\n[IMAGE UPLOADED: {filename}]"

        # 4. Text/Code Parsing
        else:
            content_str = file_bytes.decode('utf-8', errors='ignore')
            
    except Exception as e:
        logger.error(f"File parse error: {e}")
        return f"[Error reading file {filename}]"
        
    return f"\n=== CONTEXT FILE: {filename} ===\n{content_str}\n"

async def execute_pollinations_request(prompt: str, system_prompt: str) -> str:
    """
    Uses Pollinations.ai (OpenAI Model) - Free & Unlimited.
    """
    full_query = f"{system_prompt}\n\nUSER REQUEST: {prompt}\n\nASSISTANT RESPONSE (JSON if coding/tool):"
    
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

def process_vfs_logic(ai_response: str, current_vfs: Dict) -> tuple[str, Dict, bool]:
    """
    Detects JSON in AI response and updates the Virtual File System.
    Returns: (Clean Message, Updated VFS, Should Open IDE)
    """
    updated_vfs = current_vfs.copy()
    clean_message = ai_response
    should_open_ide = False

    # Find JSON block
    json_match = re.search(r'```json\s*(\{.*?\})\s*```', ai_response, re.DOTALL)
    if not json_match:
        json_match = re.search(r'(\{.*"operations":.*\})', ai_response, re.DOTALL)

    if json_match:
        try:
            json_str = json_match.group(1)
            data = json.loads(json_str)
            
            operations = data.get("operations", [])
            clean_message = data.get("message", "VFS updated successfully.")
            if data.get("open_ide"):
                should_open_ide = True

            for op in operations:
                action = op.get("action")
                path = op.get("path")
                content = op.get("content")

                if action == "create" or action == "update":
                    updated_vfs[path] = content
                elif action == "delete" and path in updated_vfs:
                    del updated_vfs[path]
                    
            # If it's a tool command (like generate_image), return raw JSON for frontend
            if "command" in data or "ui_request" in data:
                return json.dumps(data), updated_vfs, False
                
        except json.JSONDecodeError:
            pass 

    return clean_message, updated_vfs, should_open_ide

# === ENDPOINTS ===

@router.post("/ask")
async def master_ai_handler(
    prompt: str = Form(...),
    tool_id: str = Form("mistral_default"),
    chat_id: Optional[str] = Form(None),
    files: List[UploadFile] = File(None),
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    """
    Master Endpoint: Text, Code (VFS), Image Context, Tool Calling.
    """
    chats = get_db_collection("chat_history")
    tools = get_db_collection("ai_tools")
    user_id = str(current_user["_id"])

    # 1. Context Building (User Info + Files)
    user_context = f"User Profile: {current_user.get('fullname')} (@{current_user.get('username')})\n"
    file_context = ""
    if files:
        for file in files:
            file_context += await parse_uploaded_file(file)

    full_prompt = f"{user_context}\n{file_context}\n\nUser Query: {prompt}"

    # 2. Load State
    vfs_state = {}
    if chat_id and ObjectId.is_valid(chat_id):
        chat = chats.find_one({"_id": ObjectId(chat_id)})
        if chat:
            vfs_state = chat.get("vfs_state", {})

    # 3. System Prompt Selection
    if tool_id == "code_editor":
        file_list = list(vfs_state.keys())
        system_prompt = f"{VFS_SYSTEM_PROMPT}\n\nEXISTING FILES: {json.dumps(file_list)}"
        if "read" in prompt.lower() or "fix" in prompt.lower():
            system_prompt += f"\n\nFILE CONTENT: {json.dumps(vfs_state)}"
    else:
        tool_db = tools.find_one({"slug": tool_id})
        system_prompt = tool_db["system_prompt"] if tool_db else "You are YUKU, a helpful AI assistant. If the user wants an image, reply with JSON command: {\"command\": \"generate_image\", \"prompt\": \"...\"}"

    # 4. Execute AI
    raw_response = await execute_pollinations_request(full_prompt, system_prompt)

    # 5. Process VFS & Logic
    final_response, vfs_state, open_ide_signal = process_vfs_logic(raw_response, vfs_state)

    # 6. Persistence
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
            "messages": [msg_payload]
        }
        res = chats.insert_one(new_chat)
        final_chat_id = str(res.inserted_id)

    return {
        "status": "success",
        "chat_id": final_chat_id,
        "data": msg_payload,
        "vfs": vfs_state,
        "open_ide": open_ide_signal
    }

@router.post("/generate-image")
async def generate_image_handler(
    prompt: str = Form(...),
    current_user: Dict = Depends(auth_utils.get_current_user),
    chat_id: Optional[str] = Form(None)
):
    """
    Flux Schnell Image Generation.
    """
    chats = get_db_collection("chat_history")
    user_id = str(current_user["_id"])

    # Enhance
    enhanced_prompt = await execute_pollinations_request(
        f"Enhance this image prompt for Flux (Photorealistic, 8k): {prompt}", 
        "You are an expert prompt engineer."
    )

    # Generate
    ts = str(int(time.time()))
    safe_prompt = urllib.parse.quote(enhanced_prompt)
    url = f"https://flux-schnell.hello-kaiiddo.workers.dev/img?prompt={safe_prompt}&t={ts}"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=90.0)
            resp.raise_for_status()
            b64 = base64.b64encode(resp.content).decode('utf-8')
            data_uri = f"data:image/jpeg;base64,{b64}"
    except Exception as e:
        logger.error(f"Flux Error: {e}")
        raise HTTPException(503, "Image service unavailable.")

    # Save
    payload = {
        "user_id": user_id,
        "tool": "flux_image",
        "input": prompt,
        "image_data": data_uri,
        "timestamp": datetime.now(timezone.utc)
    }

    if chat_id and ObjectId.is_valid(chat_id):
        chats.update_one({"_id": ObjectId(chat_id)}, {"$push": {"messages": payload}})
        final_chat_id = chat_id
    else:
        res = chats.insert_one({
            "user_id": user_id, "title": "Image Gen", "messages": [payload]
        })
        final_chat_id = str(res.inserted_id)

    return {
        "status": "success",
        "chat_id": final_chat_id,
        "image_url": data_uri,
        "download_filename": f"yuku_flux_{ts}.jpg"
    }

# === RESTORED ENDPOINTS ===

@router.post("/share/{chat_id}")
async def create_share_link(chat_id: str, current_user: Dict = Depends(auth_utils.get_current_user)):
    chats = get_db_collection("chat_history")
    chat = chats.find_one({"_id": ObjectId(chat_id), "user_id": str(current_user["_id"])})
    if not chat:
        raise HTTPException(404, "Chat not found")
    
    share_token = secrets.token_urlsafe(16)
    chats.update_one({"_id": ObjectId(chat_id)}, {"$set": {"share_token": share_token, "is_public": True}})
    
    return {
        "share_url": f"https://yuku-nine.vercel.app/share/{share_token}",
        "api_access_url": f"https://giant-noell-pixelart002-1c1d1fda.koyeb.app/ai/shared/{share_token}"
    }

@router.post("/api-key/generate")
async def generate_api_key(current_user: Dict = Depends(auth_utils.get_current_user)):
    users = get_db_collection("users")
    api_key = f"sk_{secrets.token_hex(24)}"
    users.update_one({"_id": current_user["_id"]}, {"$set": {"sdk_api_key": api_key}})
    return {"api_key": api_key}

@router.post("/tools/add")
async def add_new_tool(name: str, slug: str, system_prompt: str, tool_type: str, current_user: Dict = Depends(auth_utils.get_current_user)):
    get_db_collection("ai_tools").update_one(
        {"slug": slug},
        {"$set": {"name": name, "slug": slug, "system_prompt": system_prompt, "type": tool_type}},
        upsert=True
    )
    return {"status": "Tool registered", "slug": slug}

@router.get("/chats")
async def get_user_chats(current_user: Dict = Depends(auth_utils.get_current_user)):
    """Fetch chat history for drawer."""
    chats = get_db_collection("chat_history")
    cursor = chats.find({"user_id": str(current_user["_id"])}).sort("last_updated", -1).limit(20)
    results = []
    for c in cursor:
        results.append({
            "id": str(c["_id"]),
            "title": c.get("title", "New Chat"),
            "date": c.get("last_updated", c.get("created_at"))
        })
    return results

@router.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str, current_user: Dict = Depends(auth_utils.get_current_user)):
    res = get_db_collection("chat_history").delete_one({"_id": ObjectId(chat_id), "user_id": str(current_user["_id"])})
    return {"deleted": res.deleted_count > 0}

@router.get("/health")
async def health_check():
    start = time.perf_counter()
    try:
        db.command("ping")
        status_db = "connected"
    except:
        status_db = "disconnected"
    latency = (time.perf_counter() - start) * 1_000_000
    return {"status": "legacy_mode_on", "latency_us": int(latency), "db": status_db}