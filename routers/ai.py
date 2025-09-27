import os
import google.generativeai as genai
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from auth import utils as auth_utils
from typing import Dict

# Configure the Gemini API client
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

router = APIRouter(
    prefix="/ai",
    tags=["AI Core"]
)

# Pydantic model for the request body
class AIPrompt(BaseModel):
    prompt: str

@router.post("/ask")
async def ask_gemini(
    request: AIPrompt, 
    current_user: Dict = Depends(auth_utils.get_current_user)
):
    if not request.prompt or not request.prompt.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Directive cannot be empty."
        )
    
    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(request.prompt)
        return {"response": response.text}
    except Exception as e:
        print(f"Gemini API Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not get response from Gemini Core."
        )

