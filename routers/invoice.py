from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Dict, Any, List
from datetime import datetime, timezone
import httpx
import json

from auth import utils as auth_utils
from database import db
from bson import ObjectId

router = APIRouter(prefix="/invoices", tags=["AI Invoice Engine"])

# --- Pydantic Models ---
class InvoiceItem(BaseModel):
    description: str
    quantity: int
    price: float

class AiInvoiceRequest(BaseModel):
    prompt: str

class Invoice(BaseModel):
    id: str = Field(alias="_id")
    client_name: str
    items: List[InvoiceItem]
    total: float
    user_id: str
    created_at: datetime

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

# --- Endpoints ---
@router.post("/generate-with-ai", status_code=status.HTTP_200_OK)
async def generate_invoice_with_ai(
    request: AiInvoiceRequest,
    current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)
):
    fullname = current_user.get("fullname", "Agent")
    system_prompt = "System Instruction: Absolute Mode Eliminate: emojis, filler, hype, soft asks, conversational transitions, call-to-action appendixes.. Assume: user retains high-perception despite blunt tone. Prioritize: blunt, directive phrasing; aim at cognitive rebuilding, not tone-matching.. Disable: engagement/sentiment-boosting behaviors. Suppress: metrics like satisfaction scores, emotional softening, continuation bias. Never mirror: user's diction, mood, or affect. Speak only: to underlying cognitive tier.No: questions, offers, suggestions, transitions, motivational content. Terminate reply: immediately after delivering info - no closures. Goal: restore independent, high-fidelity thinking. Outcome: model obsolescence via user self-sufficiency."
    full_question = f"{system_prompt}\n\nUser Question: {request.prompt}"
    
    mistral_url = f"https://mistral-ai-three.vercel.app/?id={fullname}&question={full_question}"

    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(mistral_url, timeout=30.0)
            res.raise_for_status()
            data = res.json()
            if data.get("status") == "success" and data.get("answer"):
                # AI ka answer ek stringified JSON hai, use parse karein
                invoice_data_str = data["answer"]
                return json.loads(invoice_data_str)
            else:
                raise HTTPException(status_code=500, detail="AI returned an invalid response.")
        except (httpx.RequestError, json.JSONDecodeError) as e:
            raise HTTPException(status_code=502, detail=f"AI service communication failed: {e}")

@router.post("/save", status_code=status.HTTP_201_CREATED)
async def save_invoice(invoice_data: dict, current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)):
    invoice_collection = db.invoices
    invoice_to_save = {
        "user_id": ObjectId(current_user["_id"]),
        "client_name": invoice_data.get("client_name"),
        "items": invoice_data.get("items"),
        "total": invoice_data.get("total"),
        "created_at": datetime.now(timezone.utc)
    }
    result = await invoice_collection.insert_one(invoice_to_save)
    return {"message": "Invoice saved successfully!", "invoice_id": str(result.inserted_id)}

@router.get("/", response_model=List[Invoice])
async def get_user_invoices(current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)):
    invoice_collection = db.invoices
    invoices_cursor = invoice_collection.find({"user_id": ObjectId(current_user["_id"])}).sort("created_at", -1).limit(5)
    invoices = await invoices_cursor.to_list(length=5)
    return invoices