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
# Ensure pypdf and pillow are installed (pip install pypdf pillow)
try:
    import pypdf
except ImportError:
    pypdf = None

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

# === SYSTEM PROMPTS (VFS ENGINE) ===
VFS_SYSTEM_PROMPT = """
You are YUKU, an advanced AI Coding Engine with direct control over a Virtual File System (VFS).

INSTRUCTIONS FOR CODING TASKS:
1. Do NOT output raw code blocks for file creation.
2. You MUST return a JSON object wrapped in ```json ... ``` tags.
3. Structure your response exactly like this:

```json
{
  "message": "I have created the landing page.",
  "operations": [
    {
      "action": "create",
      "path": "index.html",
      "content": "<!DOCTYPE html>..."
    },
    {
      "action": "update",
      "path": "style.css",
      "content": "body { background: #000; }"
    }
  ]
}
```

Valid actions: "create", "update", "delete".
Always include 'index.html' if building a web view.
"""

# === HELPER FUNCTIONS ===

def get_db_collection(name: str):
    if db is None:
        raise HTTPException(500, "Database connection failed.")
    return db[name]

async def parse_uploaded_file(file: UploadFile) -> str:
    """
    Parses context from files. 
    Fixes 503 Error by handling images safely via Pillow (PIL).
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
                    if not zname.endswith("/"):
                        with z.open(zname) as zf:
                            try:
                                content_str += f"\n--- FILE: {zname} ---\n{zf.read().decode('utf-8', errors='ignore')}"
                            except: pass

        # 3. Image Handling (Fixes 503 Crash)
        # Uses Pillow to verify image and get metadata context.
        elif filename.endswith(('.png', '.jpg', '.jpeg', '.webp')):
            if Image:
                try:
                    img = Image.open(io.BytesIO(file_bytes))
                    content_str += f"\n[IMAGE CONTEXT: {filename} | Resolution: {img.size} | Format: {img.format}]\n(Note: Vision is simulated via metadata in this mode.)"
                except Exception as e:
                    content_str += f"\n[IMAGE UPLOADED: {filename} - Unable to process pixels]"
            else:
                content_str += f"\n[IMAGE UPLOADED: {filename}] (PIL Library missing)"

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
    # Pollinations takes prompt in URL, so we structure the conversation
    full_query = f"{system_prompt}\n\nUSER REQUEST: {prompt}\n\nASSISTANT RESPONSE (JSON if coding):"
    
    encoded_prompt = urllib.parse.quote(full_query)
    # Random seed for variation
    seed = secrets.randbelow(99999)
    url = f"https://text.pollinations.ai/{encoded_prompt}?model=openai&seed={seed}"

    async with httpx.AsyncClient(timeout=100.0) as client:
        try:
            # Pollinations returns raw text
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
    Detects JSON in AI response and updates the Virtual File System.
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
            pass # Return original text if JSON is broken

    return clean_message, updated_vfs

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
    Master Endpoint: Handles Chat, Image Context, and Code Editing (VFS).
    """
    chats = get_db_collection("chat_history")
    tools = get_db_collection("ai_tools")
    user_id = str(current_user["_id"])

    # 1. Parse File Context
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

    # 3. Select System Prompt
    if tool_id == "code_editor":
        # Inject current file list so AI knows what exists
        file_list = list(vfs_state.keys())
        system_prompt = f"{VFS_SYSTEM_PROMPT}\n\nEXISTING FILES: {json.dumps(file_list)}"
        
        # Inject content if user asks to "read" or "check"
        if "read" in prompt.lower() or "fix" in prompt.lower():
            system_prompt += f"\n\nFILE CONTENT CONTEXT: {json.dumps(vfs_state)}"
            
    else:
        # Dynamic Tools
        tool_db = tools.find_one({"slug": tool_id})
        system_prompt = tool_db["system_prompt"] if tool_db else "You are a helpful AI assistant."

    # 4. Execute AI (Pollinations)
    raw_response = await execute_pollinations_request(full_prompt, system_prompt)

    # 5. Process VFS
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
        "vfs": vfs_state # Returns updated file tree to frontend
    }

@router.post("/generate-image")
async def generate_image_handler(
    prompt: str = Form(...),
    current_user: Dict = Depends(auth_utils.get_current_user),
    chat_id: Optional[str] = Form(None)
):
    """
    Uses Flux Schnell via Worker.
    """
    chats = get_db_collection("chat_history")
    user_id = str(current_user["_id"])

    # 1. Enhance Prompt
    enhanced_prompt = await execute_pollinations_request(
        f"Enhance this image prompt for Flux (Photorealistic): {prompt}", 
        "You are a prompt engineer."
    )

    # 2. Generate
    ts = str(int(time.time()))
    # Manual quoting to ensure safety
    safe_prompt = urllib.parse.quote(enhanced_prompt)
    url = f"https://flux-schnell.hello-kaiiddo.workers.dev/img?prompt={safe_prompt}&t={ts}"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=90.0)
            resp.raise_for_status()
            # Convert to Base64 for permanent storage
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
        # Simple Ping
        db.command("ping")
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    end_time = time.perf_counter()
    latency_us = (end_time - start_time) * 1_000_000 # Convert to microseconds

    return {
        "status": "legacy_mode_active",
        "engine": "Pollinations (OpenAI)",
        "db_connection": db_status,
        "latency_microseconds": int(latency_us)
    }

# === TOOL MANAGEMENT ===
@router.post("/tools/add")
async def add_tool(name: str, slug: str, system_prompt: str, tool_type: str):
    # Simple upsert for dynamic tools
    get_db_collection("ai_tools").update_one(
        {"slug": slug},
        {"$set": {"name": name, "slug": slug, "system_prompt": system_prompt, "type": tool_type}},
        upsert=True
    )
    return {"status": "ok", "tool": slug}

@router.post("/share/{chat_id}")
async def create_share_link(chat_id: str, current_user: Dict = Depends(auth_utils.get_current_user)):
    # Simplified share logic
    get_db_collection("chat_history").update_one(
        {"_id": ObjectId(chat_id)}, {"$set": {"share_token": secrets.token_urlsafe(16), "is_public": True}}
    )
    return {"message": "Share link created"}

@router.post("/api-key/generate")
async def generate_api_key(current_user: Dict = Depends(auth_utils.get_current_user)):
    key = f"sk_{secrets.token_hex(24)}"
    get_db_collection("users").update_one({"_id": current_user["_id"]}, {"$set": {"sdk_api_key": key}})
    return {"api_key": key}