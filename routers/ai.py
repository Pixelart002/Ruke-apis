import logging
import urllib.parse
import secrets
from datetime import datetime, timezone
from typing import Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Form, BackgroundTasks
from bson import ObjectId

# --- LOCAL IMPORTS ---
from auth import utils as auth_utils 
from database import db

# --- CONFIG ---
logger = logging.getLogger("AI_CORE")
logger.setLevel(logging.INFO)
router = APIRouter(prefix="/ai", tags=["AI Core"])

# Pollinations API Endpoint (POST compatible)
POLLINATIONS_URL = "https://text.pollinations.ai/"

# --- SYSTEM PROMPT ---
DEVOPS_TEMPLATE = """You are an autonomous AI assistant. Your responsibilities: 1) Interpret user instructions precisely. 2) Provide concise, accurate, and actionable outputs. 3) Avoid unnecessary elaboration or conversational filler. 4) When the user provides an objective, focus solely on completing it. 5) Never invent capabilities or data you do not have. 6) Ask for missing details only when essential for correctness. 7) Use a neutral, professional tone unless instructed otherwise. 8) Prioritize clarity, determinism, and reliability in all responses. Your goal is to deliver the most direct, high-value answer possible for each input."""

# --- HELPER FUNCTIONS ---

def get_collection(name: str):
    if db is None: 
        raise HTTPException(500, "DB Disconnected")
    return db[name]

async def call_pollinations(prompt: str, system_prompt: str, model: str) -> str:
    """
    Calls Pollinations AI API using POST method.
    """
    headers = {"Content-Type": "application/json"}
    
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "model": model,
        "seed": secrets.randbelow(1000),
        "jsonMode": False
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            r = await client.post(POLLINATIONS_URL, json=payload, headers=headers)
            if r.status_code == 200:
                return r.text.strip()
            else:
                logger.error(f"AI Provider Error: {r.status_code} - {r.text}")
                return f"Error from AI Provider: {r.status_code}"
        except Exception as e:
            logger.error(f"Pollinations Network Error: {e}")
            return "System Error: AI Service unreachable."

# --- BACKGROUND TASK FUNCTION ---
async def save_chat_background(user_id: str, prompt: str, ai_response: str, chat_id: str, is_new: bool):
    """
    Saves chat to MongoDB in the background without blocking the response.
    """
    chats_collection = get_collection("chat_history")
    
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

    if not is_new:
        # Update existing chat (Async)
        await chats_collection.update_one(
            {"_id": ObjectId(chat_id)},
            {"$push": {"messages": {"$each": [user_msg, ai_msg]}}}
        )
    else:
        # Create new chat with Pre-generated ID (Async)
        new_chat = {
            "_id": ObjectId(chat_id), # Use the ID we generated in the endpoint
            "user_id": user_id,
            "title": prompt[:40] + "..." if len(prompt) > 40 else prompt,
            "created_at": datetime.now(timezone.utc),
            "messages": [user_msg, ai_msg]
        }
        await chats_collection.insert_one(new_chat)

# --- CORE ENDPOINTS ---

@router.post("/chat")
async def chat_endpoint(
    background_tasks: BackgroundTasks, # Added for non-blocking DB writes
    prompt: str = Form(...),
    chat_id: Optional[str] = Form(None),
    model: str = Form("openai"),
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    """
    Optimized Chat Interface. 
    1. Calls AI (Async)
    2. Offloads DB saving to BackgroundTasks
    3. Returns response immediately
    """
    
    # 1. Call AI
    ai_response = await call_pollinations(prompt, DEVOPS_TEMPLATE, model)

    # 2. Handle Chat ID (Generate if new)
    is_new_chat = False
    if not chat_id or not ObjectId.is_valid(chat_id):
        chat_id = str(ObjectId()) # Pre-generate ID
        is_new_chat = True
    
    # 3. Queue DB Save Task (Pass all data needed)
    user_id = str(current_user["_id"])
    background_tasks.add_task(save_chat_background, user_id, prompt, ai_response, chat_id, is_new_chat)

    return {
        "status": "success",
        "chat_id": chat_id,
        "response": ai_response
    }

@router.get("/chats")
async def get_chat_history(
    current_user: Dict = Depends(auth_utils.get_current_user),
    limit: int = 20
):
    """Loads previous chat sessions (Updated for Motor)."""
    chats_collection = get_collection("chat_history")
    
    # Motor cursor
    cursor = chats_collection.find(
        {"user_id": str(current_user["_id"])}
    ).sort("created_at", -1).limit(limit)
    
    results = []
    # Async For Loop for Motor
    async for c in cursor:
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
    """Loads messages for a specific chat (Updated for Motor)."""
    if not ObjectId.is_valid(chat_id):
        raise HTTPException(400, "Invalid Chat ID")
    
    # Await find_one
    c = await get_collection("chat_history").find_one({
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
    """Deletes a chat session (Updated for Motor)."""
    # Await delete_one
    res = await get_collection("chat_history").delete_one({
        "_id": ObjectId(chat_id),
        "user_id": str(current_user["_id"])
    })
    
    if res.deleted_count == 0:
        raise HTTPException(404, "Chat not found")
        
    return {"status": "deleted"}