import os
import time
import json
import logging
import urllib.parse
import base64
import io
import secrets
import zipfile
from typing import Dict, List, Optional, Any, Union
from enum import Enum
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from bson import ObjectId

# === LIBRARIES FOR FILE PARSING ===
try:
    import pypdf
except ImportError:
    pypdf = None # Graceful fallback

from auth import utils as auth_utils 

# === DATABASE IMPORT ===
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

# === DATA MODELS ===

class ToolType(str, Enum):
    TEXT = "text"      # Pollinations (Was Mistral)
    IMAGE = "image"    # Flux
    EDITOR = "editor"  # Code Editor / VFS
    REVIEW = "review"  # Code Reviewer

class VFSActionType(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    READ = "read"

class VFSRequest(BaseModel):
    filename: str
    content: Optional[str] = None
    action: VFSActionType

class AIRequest(BaseModel):
    prompt: str
    tool_id: str = "default_mistral" # Dynamic Tool ID from DB
    chat_id: Optional[str] = None # If None, creates new chat
    context_files: Optional[List[str]] = None # List of file contents parsed frontend side or IDs

# === HELPER FUNCTIONS ===

def get_db_collection(name: str):
    if db is None:
        raise HTTPException(500, "Database connection failed.")
    return db[name]

async def parse_uploaded_file(file: UploadFile) -> str:
    """Parses PDF, TXT, ZIP into a text string for the AI context."""
    content_str = ""
    filename = file.filename.lower()
    
    try:
        file_bytes = await file.read()
        
        if filename.endswith(".pdf") and pypdf:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            for page in reader.pages:
                content_str += page.extract_text() + "\n"
        
        elif filename.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                for zname in z.namelist():
                    if not zname.endswith("/"): # Skip directories
                        with z.open(zname) as zf:
                            try:
                                content_str += f"\n--- FILE: {zname} ---\n"
                                content_str += zf.read().decode('utf-8', errors='ignore')
                            except:
                                pass
        else:
            # Assume text/code
            content_str = file_bytes.decode('utf-8', errors='ignore')
            
    except Exception as e:
        logger.error(f"File parse error: {e}")
        return f"[Error reading file {filename}]"
        
    return f"\n=== CONTEXT FILE: {filename} ===\n{content_str}\n"

async def fetch_dynamic_system_prompt(tool_id: str) -> str:
    """Fetches the system prompt dynamically from the DB."""
    tools = get_db_collection("ai_tools")
    tool = tools.find_one({"slug": tool_id})
    
    if not tool:
        # Fallback defaults if DB entry missing
        if "image" in tool_id:
            return "Professionalize this prompt for a realistic render."
        return "You are an advanced AI assistant. Provide concise, accurate answers."
        
    return tool.get("system_prompt", "")

async def execute_mistral_request(user_id: str, prompt: str, system_prompt: str) -> str:
    """
    Executes request using Pollinations.ai (Replacing Mistral).
    Robust, Free, and High Speed.
    """
    # Combine System + User Prompt
    full_prompt = f"{system_prompt}\n\nUser: {prompt}\n\nAI:"
    
    # Pollinations URL Construction
    encoded_prompt = urllib.parse.quote(full_prompt)
    # We use model=openai (or search) for best reasoning
    target_url = f"https://text.pollinations.ai/{encoded_prompt}?model=openai&seed={secrets.randbelow(99999)}"

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            # Pollinations GET request returns raw text
            resp = await client.get(target_url)
            resp.raise_for_status()
            
            # Pollinations returns direct text, so we just return content
            return resp.text.strip()
                
        except Exception as e:
            logger.error(f"Pollinations AI Error: {e}")
            return f"AI service error: {str(e)}"

# === CORE ENDPOINTS ===

@router.post("/ask")
async def master_ai_handler(
    prompt: str = Form(...),
    tool_id: str = Form("mistral_default"),
    chat_id: Optional[str] = Form(None),
    files: List[UploadFile] = File(None),
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    """
    Master Endpoint: Handles Text, Code Editing, and File Context.
    """
    chats = get_db_collection("chat_history")
    tools = get_db_collection("ai_tools")
    
    user_id = str(current_user["_id"])
    
    # 1. Prepare Context (Files)
    file_context = ""
    if files:
        for file in files:
            file_context += await parse_uploaded_file(file)
            
    final_prompt = f"{file_context}\n\n{prompt}"
    
    # 2. Identify Tool & Logic
    tool_config = tools.find_one({"slug": tool_id})
    
    if not tool_config:
        if tool_id == "mistral_default":
            tool_config = {"type": "text", "slug": "mistral_default", "system_prompt": "You are a helpful assistant."}
        elif tool_id == "code_editor":
            tool_config = {"type": "editor", "slug": "code_editor", "system_prompt": "You are a Coding Expert. Return ONLY valid XML/JSON blocks for file operations."}
        elif tool_id == "image": 
            # Fallback if frontend sends just 'image' as tool_id
            tool_config = {"type": "image", "slug": "image_gen"} 
        else:
            raise HTTPException(404, "Tool not found")

    response_payload = {
        "user_id": user_id,
        "tool": tool_id,
        "timestamp": datetime.now(timezone.utc),
        "input": prompt,
        "files_processed": [f.filename for f in files] if files else []
    }

    # 3. Execution Logic based on Type
    if tool_config.get("type") == "image":
        # Redirect to image handler logic internally
        return await generate_image_handler(prompt, current_user, chat_id)

    elif tool_config.get("type") == "editor":
        # VFS Logic
        chat_obj = chats.find_one({"_id": ObjectId(chat_id)}) if chat_id else None
        vfs_state = chat_obj.get("vfs_state", {}) if chat_obj else {}
        
        vfs_context = f"\nCURRENT FILE SYSTEM STATE: {json.dumps(list(vfs_state.keys()))}"
        system_prompt = tool_config.get("system_prompt") + vfs_context
        
        raw_response = await execute_mistral_request(user_id, final_prompt, system_prompt)
        
        response_payload["response"] = raw_response
        response_payload["vfs_update"] = True 

    else:
        # Standard Text / Pollinations
        system_prompt = tool_config.get("system_prompt", "")
        response_text = await execute_mistral_request(user_id, final_prompt, system_prompt)
        response_payload["response"] = response_text

    # 4. Database Persistence
    if chat_id and ObjectId.is_valid(chat_id):
        chats.update_one(
            {"_id": ObjectId(chat_id)},
            {
                "$push": {"messages": response_payload},
                "$set": {"last_updated": datetime.now(timezone.utc)}
            }
        )
        final_chat_id = chat_id
    else:
        new_chat = {
            "user_id": user_id,
            "title": prompt[:30] + "...",
            "created_at": datetime.now(timezone.utc),
            "vfs_state": {},
            "messages": [response_payload]
        }
        res = chats.insert_one(new_chat)
        final_chat_id = str(res.inserted_id)

    return {
        "status": "success",
        "chat_id": final_chat_id,
        "data": response_payload
    }

@router.post("/generate-image")
async def generate_image_handler(
    prompt: str = Form(...),
    current_user: Dict = Depends(auth_utils.get_current_user),
    chat_id: Optional[str] = Form(None)
):
    """
    Generates image via Flux.
    """
    chats = get_db_collection("chat_history")
    user_id = str(current_user["_id"])
    
    # 1. Enhance Prompt via Pollinations (reusing the function)
    enhancer_prompt = f"Refine this prompt for an AI image generator (Flux) to be photorealistic: {prompt}"
    enhanced_prompt = await execute_mistral_request(user_id, enhancer_prompt, "You are a prompt engineer.")
    
    # 2. Call Flux
    timestamp = str(int(time.time()))
    flux_url = f"https://flux-schnell.hello-kaiiddo.workers.dev/img?prompt={urllib.parse.quote(enhanced_prompt)}&t={timestamp}"
    
    # 3. Download & Convert to Base64
    try:
        async with httpx.AsyncClient() as client:
            img_resp = await client.get(flux_url, timeout=90.0)
            img_resp.raise_for_status()
            image_bytes = img_resp.content
            
            b64_string = base64.b64encode(image_bytes).decode('utf-8')
            data_uri = f"data:image/jpeg;base64,{b64_string}"
            
    except Exception as e:
        logger.error(f"Image Gen Failed: {e}")
        raise HTTPException(503, "Image generation failed.")

    # 4. Save to DB
    message_payload = {
        "user_id": user_id,
        "tool": "flux_image",
        "input": prompt,
        "enhanced_prompt": enhanced_prompt,
        "image_data": data_uri, 
        "timestamp": datetime.now(timezone.utc)
    }

    if chat_id and ObjectId.is_valid(chat_id):
        chats.update_one({"_id": ObjectId(chat_id)}, {"$push": {"messages": message_payload}})
        final_chat_id = chat_id
    else:
        res = chats.insert_one({
            "user_id": user_id,
            "title": "Image Generation",
            "messages": [message_payload]
        })
        final_chat_id = str(res.inserted_id)

    return {
        "status": "success",
        "chat_id": final_chat_id,
        "image_url": data_uri, 
        "download_filename": f"gen_{timestamp}.jpg"
    }

@router.post("/tools/add")
async def add_new_tool(
    name: str,
    slug: str,
    system_prompt: str,
    tool_type: ToolType,
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    tools = get_db_collection("ai_tools")
    new_tool = {
        "name": name,
        "slug": slug,
        "system_prompt": system_prompt,
        "type": tool_type,
        "created_by": current_user["_id"],
        "created_at": datetime.now(timezone.utc)
    }
    tools.update_one({"slug": slug}, {"$set": new_tool}, upsert=True)
    return {"status": "Tool registered", "slug": slug}

@router.post("/share/{chat_id}")
async def create_share_link(
    chat_id: str,
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    chats = get_db_collection("chat_history")
    chat = chats.find_one({"_id": ObjectId(chat_id), "user_id": str(current_user["_id"])})
    if not chat:
        raise HTTPException(404, "Chat not found")
    share_token = secrets.token_urlsafe(16)
    chats.update_one(
        {"_id": ObjectId(chat_id)},
        {"$set": {"share_token": share_token, "is_public": True}}
    )
    return {
        "share_url": f"{FRONTEND_URL}/share/{share_token}",
        "api_access_url": f"{BACKEND_URL}/ai/shared/{share_token}"
    }

@router.post("/api-key/generate")
async def generate_api_key(current_user: Dict = Depends(auth_utils.get_current_user)):
    users = get_db_collection("users")
    api_key = f"sk_{secrets.token_hex(24)}"
    users.update_one(
        {"_id": current_user["_id"]},
        {"$set": {"sdk_api_key": api_key}}
    )
    return {"api_key": api_key}

@router.get("/health")
async def health_check():
    """
    Health Check with Microseconds Latency.
    """
    start_time = time.time()
    
    # Minimal DB check (optional)
    status_db = "connected" if db is not None else "disconnected"
    
    end_time = time.time()
    latency_us = int((end_time - start_time) * 1_000_000) # Convert to Microseconds
    
    return {
        "status": "online", 
        "engine": "Pollinations+Flux",
        "database": status_db,
        "latency_us": latency_us
    }