# File: routers/notifications.py
# FINAL version with DUAL MODE image support (HttpUrl or str)

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, HttpUrl
from pywebpush import webpush, WebPushException
from typing import Dict, Any, Optional, Union # <-- Union ko import karein
import os
import json

from auth import utils as auth_utils
from database import user_collection
from bson import ObjectId

router = APIRouter(prefix="/webpush", tags=["Web Push Notifications"])

VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY")
VAPID_CLAIMS = {"sub": f"mailto:{os.getenv('EMAIL_FROM', '9013ms@gmail.com')}"}

# --- Models updated for DUAL MODE image support ---
class BroadcastMessage(BaseModel):
    title: str
    body: str
    # Ab yeh HttpUrl ya str, dono ko accept karega
    image: Optional[Union[HttpUrl, str]] = None 

class CustomNotification(BaseModel):
    target_emtail: EmailStr
    title: str
    body: str
    # Ab yeh HttpUrl ya str, dono ko accept karega
    image: Optional[Union[HttpUrl, str]] = None

# --- Helper function to build the payload ---
def build_message_data(title: str, body: str, image: Optional[Union[HttpUrl, str]] = None) -> str:
    payload = {"title": title, "body": body}
    if image:
        # str() function HttpUrl aur str, dono ko aasaani se handle kar leta hai
        payload["image"] = str(image)
    return json.dumps(payload)

# --- (GET /vapid-public-key and POST /subscribe endpoints remain the same) ---
@router.get("/vapid-public-key")
def get_vapid_public_key():
    if not VAPID_PUBLIC_KEY:
        raise HTTPException(status_code=500, detail="VAPID public key not configured.")
    return {"public_key": VAPID_PUBLIC_KEY}

@router.post("/subscribe", status_code=status.HTTP_201_CREATED)
async def subscribe(subscription: BaseModel, current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)):
    user_id = ObjectId(current_user["_id"])
    # Pydantic v1 mein .dict() use hota hai, v2 mein .model_dump()
    sub_dict = subscription.dict() if hasattr(subscription, 'dict') else subscription.model_dump()
    user_collection.update_one({"_id": user_id}, {"$set": {"webpush_subscription": sub_dict}})
    return {"message": "Successfully subscribed."}


# --- (send-test endpoint remains the same) ---
@router.post("/send-test", status_code=status.HTTP_200_OK)
async def send_test_notification(current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)):
    user_id = ObjectId(current_user["_id"])
    user = user_collection.find_one({"_id": user_id})
    if not user or "webpush_subscription" not in user:
        raise HTTPException(status_code=404, detail="User subscription not found.")
    
    subscription_info = user["webpush_subscription"]
    message_data = json.dumps({"title": "YUKU Protocol Test", "body": "This notification is working!"})
    
    try:
        webpush(
            subscription_info=subscription_info,
            data=message_data,
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims=VAPID_CLAIMS
        )
        return {"message": "Test notification sent successfully!"}
    except WebPushException as ex:
        raise HTTPException(status_code=500, detail=str(ex))


# --- Updated Custom Notification Endpoint ---
@router.post("/send-custom", status_code=status.HTTP_200_OK)
async def send_custom_notification(
    notification: CustomNotification,
    current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)
):
    target_user = user_collection.find_one({"email": notification.target_email})
    if not target_user or "webpush_subscription" not in target_user:
        raise HTTPException(status_code=404, detail=f"Subscription not found for user: {notification.target_email}")

    subscription_info = target_user["webpush_subscription"]
    message_data = build_message_data(notification.title, notification.body, notification.image)
    
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

# --- Updated Broadcast Endpoint ---
@router.post("/broadcast", status_code=status.HTTP_200_OK)
def broadcast_notification(
    message: BroadcastMessage,
    current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)
):
    subscribed_users = user_collection.find({"webpush_subscription": {"$exists": True}})
    success_count = 0
    failure_count = 0
    message_data = build_message_data(message.title, message.body, message.image)
    
    for user in subscribed_users:
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

