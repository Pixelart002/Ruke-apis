import logging
import urllib.parse
import secrets
from datetime import datetime, timezone
from typing import Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Form
from bson import ObjectId

# --- LOCAL IMPORTS ---
from auth import utils as auth_utils 
from database import db

# --- CONFIG ---
logger = logging.getLogger("AI_CORE")
logger.setLevel(logging.INFO)
router = APIRouter(prefix="/ai", tags=["AI Core"])

POLLINATIONS_URL = "https://text.pollinations.ai/"

# --- SYSTEM PROMPT ---
DEVOPS_TEMPLATE = """


You are an autonomous AI assistant. Your responsibilities: 1) Interpret user instructions precisely. 2) Provide concise, accurate, and actionable outputs. 3) Avoid unnecessary elaboration or conversational filler. 4) When the user provides an objective, focus solely on completing it. 5) Never invent capabilities or data you do not have. 6) Ask for missing details only when essential for correctness. 7) Use a neutral, professional tone unless instructed otherwise. 8) Prioritize clarity, determinism, and reliability in all responses. Your goal is to deliver the most direct, high-value answer possible for each input.
 
"""

# --- HELPER FUNCTIONS ---

def get_collection(name: str):
    if db is None: 
        raise HTTPException(500, "DB Disconnected")
    return db[name]

async def call_pollinations(prompt: str, system_prompt: str, model: str) -> str:
    """Calls Pollinations AI API."""
    full_prompt = f"{system_prompt}\n\nUSER QUERY: {prompt}"
    encoded_prompt = urllib.parse.quote(full_prompt)
    url = f"{POLLINATIONS_URL}{encoded_prompt}?model={model}&seed={secrets.randbelow(1000)}"

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            r = await client.get(url)
            if r.status_code == 200:
                return r.text.strip()
            else:
                return f"Error from AI Provider: {r.status_code}"
        except Exception as e:
            logger.error(f"Pollinations Network Error: {e}")
            return "System Error: AI Service unreachable."

# --- CORE ENDPOINTS ---

@router.post("/chat")
async def chat_endpoint(
    prompt: str = Form(...),
    chat_id: Optional[str] = Form(None),
    model: str = Form("openai"),
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    """
    Simple Chat Interface. 
    Handles: Text Input + AI Response + History Saving.
    """
    chats_collection = get_collection("chat_history")

    # 1. Call AI
    ai_response = await call_pollinations(prompt, DEVOPS_TEMPLATE, model)

    # 2. Prepare Messages
    user_msg = {
        "role": "user",
        "content": prompt,
        "timestamp": datetime.now(timezone.utc)
    }
    
    ai_msg = {
        "role": "assistant",
        "content": ai_response,
        "timestamp": datetime.now(timezone.utc)
    }

    # 3. Save to Database
    if chat_id and ObjectId.is_valid(chat_id):
        # Update existing chat
        chats_collection.update_one(
            {"_id": ObjectId(chat_id)},
            {"$push": {"messages": {"$each": [user_msg, ai_msg]}}}
        )
        final_chat_id = chat_id
    else:
        # Create new chat
        new_chat = {
            "user_id": str(current_user["_id"]),
            "title": prompt[:40] + "..." if len(prompt) > 40 else prompt,
            "created_at": datetime.now(timezone.utc),
            "messages": [user_msg, ai_msg]
        }
        res = chats_collection.insert_one(new_chat)
        final_chat_id = str(res.inserted_id)

    return {
        "status": "success",
        "chat_id": final_chat_id,
        "response": ai_response
    }

@router.get("/chats")
async def get_chat_history(
    current_user: Dict = Depends(auth_utils.get_current_user),
    limit: int = 20
):
    """Loads previous chat sessions for the sidebar."""
    chats_collection = get_collection("chat_history")
    
    cursor = chats_collection.find(
        {"user_id": str(current_user["_id"])}
    ).sort("created_at", -1).limit(limit)
    
    results = []
    for c in cursor:
        results.append({
            "id": str(c["_id"]),
            "title": c.get("title", "Untitled Chat"),
            "date": c.get("created_at")
        })
        
    return results

@router.get("/chats/{chat_id}")
async def get_single_chat(
    chat_id: str,
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    """Loads messages for a specific chat."""
    if not ObjectId.is_valid(chat_id):
        raise HTTPException(400, "Invalid Chat ID")
        
    c = get_collection("chat_history").find_one({
        "_id": ObjectId(chat_id),
        "user_id": str(current_user["_id"])
    })
    
    if not c:
        raise HTTPException(404, "Chat not found")
        
    c["id"] = str(c["_id"])
    del c["_id"]
    
    return c

@router.delete("/chats/{chat_id}")
async def delete_chat(
    chat_id: str,
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    """Deletes a chat session."""
    res = get_collection("chat_history").delete_one({
        "_id": ObjectId(chat_id),
        "user_id": str(current_user["_id"])
    })
    
    if res.deleted_count == 0:
        raise HTTPException(404, "Chat not found")
        
    return {"status": "deleted"}