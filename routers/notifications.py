# File: routers/notifications.py
# FINAL version using the reliable 'pywebpush' library

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
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

class WebPushSubscription(BaseModel):
    endpoint: str
    keys: Dict[str, str]

@router.get("/vapid-public-key")
def get_vapid_public_key():
    if not VAPID_PUBLIC_KEY:
        raise HTTPException(status_code=500, detail="VAPID public key not configured.")
    return {"public_key": VAPID_PUBLIC_KEY}

@router.post("/subscribe", status_code=status.HTTP_201_CREATED)
async def subscribe(subscription: WebPushSubscription, current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)):
    user_id = ObjectId(current_user["_id"])
    user_collection.update_one({"_id": user_id}, {"$set": {"webpush_subscription": subscription.dict()}})
    return {"message": "Successfully subscribed."}

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
        
        
        
        
        
        
        
        
        
        
        
        
 router.post("/broadcast", status_code=status.HTTP_200_OK)
async def broadcast_notification(
    message: BroadcastMessage, # Ab yeh line kaam karegi
    current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)
):
    subscribed_users = user_collection.find({"webpush_subscription": {"$exists": True}})
    
    success_count = 0
    failure_count = 0
    
    message_data = json.dumps({"title": message.title, "body": message.body})
    
    # Using async for with motor cursor
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
        except WebPushException as ex:
            print(f"Failed to send notification to user {user['_id']}: {ex}")
            failure_count += 1

    return {
        "message": "Broadcast attempt finished.",
        "sent_successfully": success_count,
        "failed_to_send": failure_count
    }