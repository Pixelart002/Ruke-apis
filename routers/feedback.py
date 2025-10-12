from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, constr
from typing import Dict, Any, List
from datetime import datetime, timezone
import os

from auth import utils as auth_utils
from database import db  # Assuming 'db' is your MongoDB database instance
from bson import ObjectId

router = APIRouter(prefix="/feedback", tags=["Feedback"])

# --- Pydantic Models ---
class FeedbackCreate(BaseModel):
    rating: int
    comment: constr(min_length=10, max_length=500)

class FeedbackResponse(FeedbackCreate):
    id: str
    username: str
    created_at: datetime

# --- Endpoints ---
@router.post("/", status_code=status.HTTP_201_CREATED)
# CHANGE 1: Changed 'async def' to 'def'
def submit_feedback(
    feedback: FeedbackCreate,
    current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)
):
    """
    Allows a logged-in user to submit feedback.
    """
    feedback_collection = db.feedback
    
    user_id = ObjectId(current_user["_id"])

    # --- START: ADD THIS SNIPPET ---
    # Check if feedback from this user already exists
    existing_feedback = feedback_collection.find_one({"user_id": user_id})
    if existing_feedback:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already submitted feedback."
        )
    # --- END: ADD THIS SNIPPET ---


    new_feedback = {
        "user_id": ObjectId(current_user["_id"]),
        "username": current_user["username"],
        "rating": feedback.rating,
        "comment": feedback.comment,
        "created_at": datetime.now(timezone.utc)
    }
    
    # CHANGE 2: Removed 'await' because insert_one is synchronous
    feedback_collection.insert_one(new_feedback)
    
    return {"message": "Thank you for your feedback!"}

@router.get("/", response_model=List[FeedbackResponse])
# CHANGE 3: Changed 'async def' to 'def'
def get_all_feedback():
    """
    Fetches all submitted feedback to display publicly as testimonials.
    """
    feedback_collection = db.feedback
    
    feedbacks_cursor = feedback_collection.find().sort("created_at", -1).limit(20)
    
    feedback_list = []
    # CHANGE 4: Changed 'async for' to a standard 'for' loop
    for feedback_doc in feedbacks_cursor:
        feedback_list.append(FeedbackResponse(
            id=str(feedback_doc["_id"]),
            username=feedback_doc["username"],
            rating=feedback_doc["rating"],
            comment=feedback_doc["comment"],
            created_at=feedback_doc["created_at"]
        ))
        
    return feedback_list