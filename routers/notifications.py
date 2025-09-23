# File: routers/notifications.py

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
import firebase_admin
from firebase_admin import credentials, messaging
from typing import Dict, Any

from auth import utils as auth_utils
from database import user_collection
from bson import ObjectId

router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"]
)

class SubscriptionRequest(BaseModel):
    fcm_token: str

@router.post("/subscribe", status_code=status.HTTP_200_OK)
async def subscribe_for_notifications(req: SubscriptionRequest, current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)):
    """
    Saves a user's FCM token to their profile for push notifications.
    """
    user_id = ObjectId(current_user["_id"])
    
    # User ke document mein FCM token save/update karein
    result = user_collection.update_one(
        {"_id": user_id},
        {"$set": {"fcm_token": req.fcm_token}}
    )

    if result.modified_count == 0 and result.matched_count == 0:
         raise HTTPException(status_code=404, detail="User not found")

    return {"message": "Successfully subscribed to notifications."}


@router.post("/send-test", status_code=status.HTTP_200_OK)
async def send_test_notification(current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)):
    """
    Sends a test push notification to the currently logged-in user.
    """
    user_id = ObjectId(current_user["_id"])
    user = user_collection.find_one({"_id": user_id})

    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    fcm_token = user.get("fcm_token")
    if not fcm_token:
        raise HTTPException(status_code=400, detail="User has not subscribed for notifications.")

    # Construct the notification message
    message = messaging.Message(
        notification=messaging.Notification(
            title='YUKU Protocol Test',
            body='This is a test notification from your YUKU Mission Control!',
        ),
        token=fcm_token,
        webpush=messaging.WebpushConfig(
            fcm_options=messaging.WebpushFCMOptions(
                link='/#dashboard' # Optional: Link to open when notification is clicked
            )
        )
    )
    
    try:
        # Send the message
        response = messaging.send(message)
        print(f"Successfully sent message: {response}")
        return {"message": "Test notification sent successfully!"}
    except Exception as e:
        print(f"Error sending notification: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send notification: {e}")