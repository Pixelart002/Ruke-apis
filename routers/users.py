# routers/users.py

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict

# --- YEH IMPORTS ZAROORI HAIN ---
from auth import utils as auth_utils, schemas as auth_schemas
from database import user_collection
# --- IMPORTS KHATM ---

router = APIRouter(
    prefix="/users",
    tags=["Users"]
)

@router.get("/me", response_model=auth_schemas.UserInfo)
async def read_users_me(current_user: Dict = Depends(auth_utils.get_current_user)):
    # Yeh function ab sahi hai (Dependency handle karegi async fetch)
    return {
        "userId": str(current_user["_id"]),
        "username": current_user.get("username", "N/A"),
        "fullname": current_user["fullname"],
        "email": current_user["email"]
    }

@router.put("/me")
async def update_user_me(user_update: auth_schemas.UserUpdate, current_user: Dict = Depends(auth_utils.get_current_user)):
    
    # Check if the new username is already taken by ANOTHER user
    if user_update.username != current_user.get("username"):
        # Added await
        if await user_collection.find_one({"username": user_update.username}):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This username is already taken."
            )
            
    # Update the user document in the database
    # Added await
    await user_collection.update_one(
        {"_id": current_user["_id"]},
        {"$set": {
            "fullname": user_update.fullname,
            "username": user_update.username
        }}
    )
    
    return {"message": "Profile updated successfully!"}