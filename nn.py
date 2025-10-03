# File: routers/notifications.py
# FINAL version with custom and broadcast functionality

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from pywebpush import webpush, WebPushException
from typing import Dict, Any
import os
import json

from auth import utils as auth_utils
from database import user_collection
from bson import ObjectId

router = APIRouter(prefix="/webpush", tags=["Web Push Notifications"])

VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY")
VAPID_CLAIMS = {"sub": f"mailto:{os.getenv('EMAIL_FROM', '9013ms@gmail.com')}"}

# --- Models for different notification types ---
class WebPushSubscription(BaseModel):
    endpoint: str
    keys: Dict[str, str]

class BroadcastMessage(BaseModel):
    title: str
    body: str

class CustomNotification(BaseModel):
    target_email: EmailStr  # We will send to a specific user
    title: str
    body: str

# --- Existing Endpoints (No changes needed) ---
@router.get("/vapid-public-key")
def get_vapid_public_key():
    # ... (code is correct)
    if not VAPID_PUBLIC_KEY:
        raise HTTPException(status_code=500, detail="VAPID public key not configured.")
    return {"public_key": VAPID_PUBLIC_KEY}

@router.post("/subscribe", status_code=status.HTTP_201_CREATED)
async def subscribe(subscription: WebPushSubscription, current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)):
    # ... (code is correct)
    user_id = ObjectId(current_user["_id"])
    user_collection.update_one({"_id": user_id}, {"$set": {"webpush_subscription": subscription.dict()}})
    return {"message": "Successfully subscribed."}

# --- NEW: Custom Notification Endpoint ---
@router.post("/send-custom", status_code=status.HTTP_200_OK)
async def send_custom_notification(
    notification: CustomNotification,
    current_user: Dict[str, Any] = Depends(auth_utils.get_current_user) # Protected
):
    # Find the target user by their email
    target_user = user_collection.find_one({"email": notification.target_email})
    
    if not target_user or "webpush_subscription" not in target_user:
        raise HTTPException(status_code=404, detail=f"Subscription not found for user: {notification.target_email}")

    subscription_info = target_user["webpush_subscription"]
    message_data = json.dumps({"title": notification.title, "body": notification.body})
    
    try:
        webpush(
            subscription_info=subscription_info,
            data=message_data,
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims=VAPID_CLAIMS
        )
        return {"message": f"Successfully sent notification to {notification.target_email}"}
    except WebPushException as ex:
        raise HTTPException(status_code=500, detail=str(ex))

# --- Broadcast Endpoint (for Advertisements) ---
@router.post("/broadcast", status_code=status.HTTP_200_OK)
async def broadcast_notification(
    message: BroadcastMessage,
    current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)
):
    # ... (code is correct)
    subscribed_users = user_collection.find({"webpush_subscription": {"$exists": True}})
    success_count = 0
    failure_count = 0
    message_data = json.dumps({"title": message.title, "body": message.body})
    
    # Motor returns an async cursor, so we must iterate asynchronously
    async for user in subscribed_users:
        subscription_info = user["webpush_subscription"]
        try:
            webpush(
                subscription_info=subscription_info,
                data=message_data,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims=VAPID_CLAIMS
            )
            success_count += 1
        except WebPushException:
            failure_count += 1
    
    return {
        "message": "Broadcast finished.",
        "sent_successfully": success_count,
        "failed_to_send": failure_count
    }