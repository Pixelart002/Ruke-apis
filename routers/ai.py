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
# PDF Support
try:
    import pypdf
except ImportError:
    pypdf = None

# Image/Vision Support
try:
    from PIL import Image
    import pytesseract # Free OCR
except ImportError:
    Image = None
    pytesseract = None

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

# === CONSTANTS & SYSTEM PROMPTS ===
# Forces AI to output JSON for file operations so the VFS Engine can parse it.
VFS_SYSTEM_PROMPT = """
You are YUKU, an advanced AI Coding Engine with direct control over a Virtual File System (VFS).

INSTRUCTIONS:
1. You are capable of CREATING, UPDATING, and DELETING files in the user's environment.
2. To perform file operations, you MUST strictly output a JSON object wrapped in ```json ... ``` tags.
3. Do NOT write raw code blocks (like ```html ... ```) if you want them saved to a file. Put them inside the JSON content field.

JSON STRUCTURE:
```json
{
  "message": "I have created the requested portfolio page.",
  "operations": [
    {
      "action": "create",
      "path": "index.html",
      "content": "<!DOCTYPE html><html>...</html>"
    },
    {
      "action": "update",
      "path": "style.css",
      "content": "body { background: #050a08; color: #10b981; }"
    }
  ]
}
```
4. Valid actions: "create", "update", "delete".
5. If creating a website, always include 'index.html'.
"""

# === HELPER FUNCTIONS ===

def get_db_collection(name: str):
    if db is None:
        raise HTTPException(500, "Database connection failed.")
    return db[name]

async def parse_uploaded_file(file: UploadFile) -> str:
    """
    Parses context from files (PDF, Zip, Text, Images).
    Includes Free OCR logic (pytesseract) with safe fallbacks to prevent 503 errors.
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
            except Exception:
                content_str += "[PDF Content Unreadable]\n"

        # 2. Zip Parsing
        elif filename.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                for zname in z.namelist():
                    if not zname.endswith("/") and not zname.startswith("__MACOSX"):
                        with z.open(zname) as zf:
                            try:
                                content_str += f"\n--- FILE: {zname} ---\n{zf.read().decode('utf-8', errors='ignore')}"
                            except: pass

        # 3. Vision / Image Handling (Free OCR)
        elif filename.endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp')) and Image:
            try:
                img = Image.open(io.BytesIO(file_bytes))
                content_str += f"\n[IMAGE METADATA: {filename} | Size: {img.size} | Format: {img.format}]\n"
                
                # Try Free OCR if installed on server
                if pytesseract:
                    try:
                        text = pytesseract.image_to_string(img)
                        if text.strip():
                            content_str += f"[EXTRACTED TEXT FROM IMAGE]:\n{text}\n"
                    except Exception:
                        content_str += "(OCR Text Extraction unavailable in this environment)\n"
                else:
                    content_str += "(Visual analysis limited: Library missing)\n"
                    
            except Exception as e:
                content_str += f"\n[IMAGE UPLOADED: {filename} - Analysis Failed]"

        # 4. Text/Code Parsing
        else:
            content_str = file_bytes.decode('utf-8', errors='ignore')
            
    except Exception as e:
        logger.error(f"File parse error: {e}")
        return f"[Error reading file {filename}]"
        
    return f"\n=== CONTEXT FILE: {filename} ===\n{content_str}\n"

async def execute_pollinations_request(prompt: str, system_prompt: str) -> str:
    """
    Uses Pollinations.ai (Free OpenAI Model). 
    Unlimited, no API key required.
    """
    # Structure the prompt for Pollinations
    full_query = f"{system_prompt}\n\nUSER REQUEST: {prompt}\n\nASSISTANT RESPONSE:"
    
    encoded_prompt = urllib.parse.quote(full_query)
    # Seed ensures response consistency/variety
    seed = secrets.randbelow(999999)
    url = f"https://text.pollinations.ai/{encoded_prompt}?model=openai&seed={seed}"

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text.strip()
        except Exception as e:
            logger.error(f"Pollinations API Error: {e}")
            # Fallback JSON to prevent frontend crash
            return json.dumps({
                "message": "Error connecting to AI Engine. Please try again.",
                "operations": []
            })

def process_vfs_logic(ai_response: str, current_vfs: Dict) -> tuple[str, Dict]:
    """
    VFS ENGINE: Detects JSON code blocks and updates the file tree.
    Returns (Clean Message, Updated VFS Dictionary).
    """
    updated_vfs = current_vfs.copy()
    clean_message = ai_response

    # Regex to find JSON block inside ```json ... ```
    json_match = re.search(r'```json\s*(\{.*?\})\s*```', ai_response, re.DOTALL)
    
    # Fallback: Find raw JSON object if code blocks missing
    if not json_match:
        json_match = re.search(r'(\{.*"operations":.*\})', ai_response, re.DOTALL)

    if json_match:
        try:
            json_str = json_match.group(1)
            data = json.loads(json_str)
            
            operations = data.get("operations", [])
            clean_message = data.get("message", "VFS updated successfully.")

            for op in operations:
                action = op.get("action")
                path = op.get("path")
                content = op.get("content")

                if action == "create" or action == "update":
                    updated_vfs[path] = content
                elif action == "delete" and path in updated_vfs:
                    del updated_vfs[path]
                    
        except json.JSONDecodeError:
            # If JSON is broken, return raw text so user sees the error
            pass 

    return clean_message, updated_vfs

# === ENDPOINTS ===

@router.post("/ask")
async def master_ai_handler(
    prompt: str = Form(...),
    tool_id: str = Form("mistral_default"),
    system_prompt: Optional[str] = Form(None), # Frontend override
    chat_id: Optional[str] = Form(None),
    files: List[UploadFile] = File(None),
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    """
    Master Endpoint: Chat + VFS + Vision.
    """
    chats = get_db_collection("chat_history")
    tools = get_db_collection("ai_tools")
    user_id = str(current_user["_id"])

    # 1. Parse File Context (Context Injection)
    file_context = ""
    if files:
        for file in files:
            file_context += await parse_uploaded_file(file)

    full_prompt = f"{file_context}\n\n{prompt}"

    # 2. Load Chat & VFS State
    vfs_state = {}
    if chat_id and ObjectId.is_valid(chat_id):
        chat = chats.find_one({"_id": ObjectId(chat_id)})
        if chat:
            vfs_state = chat.get("vfs_state", {})

    # 3. Determine System Prompt
    final_sys_prompt = ""
    
    if system_prompt:
        # Frontend override (User custom settings)
        final_sys_prompt = system_prompt
    elif tool_id == "code_editor":
        # VFS Mode: Inject file list
        file_list = list(vfs_state.keys())
        final_sys_prompt = f"{VFS_SYSTEM_PROMPT}\n\nEXISTING FILES: {json.dumps(file_list)}"
        
        # Inject file content if user asks to "read"
        if "read" in prompt.lower() or "fix" in prompt.lower() or "check" in prompt.lower():
            final_sys_prompt += f"\n\nCURRENT FILE CONTENTS: {json.dumps(vfs_state)}"
    else:
        # Standard Tools
        tool_db = tools.find_one({"slug": tool_id})
        final_sys_prompt = tool_db["system_prompt"] if tool_db else "You are a helpful AI assistant."

    # 4. Execute AI (Pollinations)
    raw_response = await execute_pollinations_request(full_prompt, final_sys_prompt)

    # 5. Process VFS Logic
    final_response, vfs_state = process_vfs_logic(raw_response, vfs_state)

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
        "vfs": vfs_state # Return updated tree
    }

@router.post("/generate-image")
async def generate_image_handler(
    prompt: str = Form(...),
    current_user: Dict = Depends(auth_utils.get_current_user),
    chat_id: Optional[str] = Form(None)
):
    """
    Generates image via Flux Schnell (Worker).
    """
    chats = get_db_collection("chat_history")
    user_id = str(current_user["_id"])

    # 1. Enhance Prompt
    enhanced_prompt = await execute_pollinations_request(
        f"Enhance this image prompt for Flux (Photorealistic, 8k): {prompt}", 
        "You are a prompt engineer."
    )

    # 2. Generate
    ts = str(int(time.time()))
    safe_prompt = urllib.parse.quote(enhanced_prompt)
    url = f"https://flux-schnell.hello-kaiiddo.workers.dev/img?prompt={safe_prompt}&t={ts}"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=90.0)
            resp.raise_for_status()
            # Convert to Base64 for DB storage
            b64 = base64.b64encode(resp.content).decode('utf-8')
            data_uri = f"data:image/jpeg;base64,{b64}"
    except Exception as e:
        logger.error(f"Flux Error: {e}")
        raise HTTPException(503, "Image service unavailable.")

    # 3. Save
    payload = {
        "user_id": user_id,
        "tool": "flux_image",
        "input": prompt,
        "enhanced_prompt": enhanced_prompt,
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

@router.get("/health")
async def health_check():
    """
    Health check with Microsecond Latency.
    """
    start_time = time.perf_counter()
    
    db_status = "unknown"
    try:
        db.command("ping")
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    end_time = time.perf_counter()
    latency_us = (end_time - start_time) * 1_000_000 

    return {
        "status": "legacy_mode_active",
        "engine": "Pollinations (OpenAI)",
        "vision": "Free OCR / Metadata",
        "db_connection": db_status,
        "latency_microseconds": int(latency_us)
    }

@router.get("/me")
async def read_users_me(current_user: Dict = Depends(auth_utils.get_current_user)):
    return {
        "userId": str(current_user["_id"]),
        "username": current_user.get("username", "N/A"),
        "fullname": current_user["fullname"],
        "email": current_user["email"]
    }

# === TOOLS ===
@router.post("/tools/add")
async def add_tool(name: str, slug: str, system_prompt: str, tool_type: str):
    get_db_collection("ai_tools").update_one(
        {"slug": slug},
        {"$set": {"name": name, "slug": slug, "system_prompt": system_prompt, "type": tool_type}},
        upsert=True
    )
    return {"status": "ok", "tool": slug}

@router.post("/share/{chat_id}")
async def create_share_link(chat_id: str, current_user: Dict = Depends(auth_utils.get_current_user)):
    chats = get_db_collection("chat_history")
    token = secrets.token_urlsafe(16)
    chats.update_one({"_id": ObjectId(chat_id)}, {"$set": {"share_token": token, "is_public": True}})
    return {"share_url": f"{FRONTEND_URL}/share/{token}"}

@router.post("/api-key/generate")
async def generate_api_key(current_user: Dict = Depends(auth_utils.get_current_user)):
    users = get_db_collection("users")
    api_key = f"sk_{secrets.token_hex(24)}"
    users.update_one({"_id": current_user["_id"]}, {"$set": {"sdk_api_key": api_key}})
    return {"api_key": api_key}