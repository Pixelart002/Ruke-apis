from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, constr
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import os

from auth import utils as auth_utils
from database import db
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
    updated_at: Optional[datetime] = None # Naya field add kiya

# --- Endpoints ---
@router.post("/", status_code=status.HTTP_201_CREATED, response_model=FeedbackResponse)
def submit_feedback(
    feedback: FeedbackCreate,
    current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)
):
    """
    User ko feedback submit karne deta hai, lekin sirf ek baar.
    """
    feedback_collection = db.feedback
    user_id = ObjectId(current_user["_id"])

    # Check karein ki user ne pehle se feedback diya hai ya nahi
    existing_feedback = feedback_collection.find_one({"user_id": user_id})
    if existing_feedback:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already submitted feedback. Please edit the existing one."
        )

    new_feedback_data = {
        "user_id": user_id,
        "username": current_user["username"],
        "rating": feedback.rating,
        "comment": feedback.comment,
        "created_at": datetime.now(timezone.utc),
        "updated_at": None # Shuru mein updated_at null hoga
    }
    
    result = feedback_collection.insert_one(new_feedback_data)
    created_feedback = feedback_collection.find_one({"_id": result.inserted_id})
    
    return FeedbackResponse(
        id=str(created_feedback["_id"]),
        username=created_feedback["username"],
        rating=created_feedback["rating"],
        comment=created_feedback["comment"],
        created_at=created_feedback["created_at"],
        updated_at=created_feedback.get("updated_at")
    )

# --- START: YEH NAYA ENDPOINT ADD KIYA GAYA HAI ---
@router.put("/", response_model=FeedbackResponse)
def update_feedback(
    feedback_update: FeedbackCreate,
    current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)
):
    """
    User ko apna purana feedback update karne deta hai.
    """
    feedback_collection = db.feedback
    user_id = ObjectId(current_user["_id"])

    # Naye data ke saath 'updated_at' timestamp bhi set karein
    update_data = {
        "rating": feedback_update.rating,
        "comment": feedback_update.comment,
        "updated_at": datetime.now(timezone.utc)
    }

    # User ke 'user_id' se document dhoond kar update karein
    result = feedback_collection.update_one(
        {"user_id": user_id},
        {"$set": update_data}
    )

    # Agar uss user ka koi feedback nahi mila, to error dein
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No feedback found to update. Please submit feedback first."
        )

    updated_feedback = feedback_collection.find_one({"user_id": user_id})
    return FeedbackResponse(
        id=str(updated_feedback["_id"]),
        username=updated_feedback["username"],
        rating=updated_feedback["rating"],
        comment=updated_feedback["comment"],
        created_at=updated_feedback["created_at"],
        updated_at=updated_feedback.get("updated_at")
    )
# --- END: NAYA ENDPOINT KHATAM ---


@router.get("/", response_model=List[FeedbackResponse])
def get_all_feedback():
    """
    Saare testimonials ko fetch karta hai.
    """
    feedback_collection = db.feedback
    feedbacks_cursor = feedback_collection.find().sort("created_at", -1).limit(20)
    
    feedback_list = []
    for feedback_doc in feedbacks_cursor:
        feedback_list.append(FeedbackResponse(
            id=str(feedback_doc["_id"]),
            username=feedback_doc["username"],
            rating=feedback_doc["rating"],
            comment=feedback_doc["comment"],
            created_at=feedback_doc["created_at"],
            updated_at=feedback_doc.get("updated_at") # .get() use karna safe hai
        ))
        
    return feedback_list
