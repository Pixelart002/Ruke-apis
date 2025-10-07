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

class Feedback(FeedbackCreate):
    id: str
    username: str
    created_at: datetime

# --- Endpoints ---
@router.post("/", status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    feedback: FeedbackCreate,
    current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)
):
    """
    Allows a logged-in user to submit feedback.
    """
    feedback_collection = db.feedback  # Use a 'feedback' collection
    
    new_feedback = {
        "user_id": ObjectId(current_user["_id"]),
        "username": current_user["username"],
        "rating": feedback.rating,
        "comment": feedback.comment,
        "created_at": datetime.now(timezone.utc)
    }
    
    await feedback_collection.insert_one(new_feedback)
    return {"message": "Thank you for your feedback!"}

@router.get("/", response_model=List[Feedback])
async def get_all_feedback():
    """
    Fetches all submitted feedback to display publicly as testimonials.
    """
    feedback_collection = db.feedback
    
    # Fetch latest 10 feedbacks, sorted by newest first
    feedbacks_cursor = feedback_collection.find().sort("created_at", -1).limit(10)
    
    feedback_list = []
    async for feedback in feedbacks_cursor:
        feedback_list.append(Feedback(
            id=str(feedback["_id"]),
            username=feedback["username"],
            rating=feedback["rating"],
            comment=feedback["comment"],
            created_at=feedback["created_at"]
        ))
        
    return feedback_list