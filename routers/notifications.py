# File: routers/notifications.py

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import firebase_admin
from firebase_admin import credentials, messaging
from typing import Dict

from auth import utils as auth_utils
from database import user_collection

# --- Firebase Admin SDK ko Initialize Karein ---
# Zaroori: 'serviceAccountKey.json' file aapke project ke root mein honi chahiye
try:
    cred = credentials.Certificate("/yukuprotocol01-firebase-adminsdk-fbsvc-1ac73f33b3.json")
    firebase_admin.initialize_app(cred)
except Exception as e:
    print(f"Firebase Admin SDK initialization error: {e}")

router = APIRouter(prefix="/notifications", tags=["Notifications"])

class SubscriptionRequest(BaseModel):
    fcm_token: str

@router.post("/subscribe")
async def subscribe_for_notifications(req: SubscriptionRequest, current_user: Dict = Depends(auth_utils.get_current_user)):
    user_id = current_user["_id"]
    # User ke document mein FCM token save karein
    user_collection.update_one(
        {"_id": user_id},
        {"$set": {"fcm_token": req.fcm_token}}
    )
    return {"message": "Subscribed to notifications successfully"}

# Test ke liye yeh endpoint bana sakte hain
@router.post("/send-test")
async def send_test_notification(current_user: Dict = Depends(auth_utils.get_current_user)):
    user = user_collection.find_one({"_id": current_user["_id"]})
    fcm_token = user.get("fcm_token")
    if not fcm_token:
        raise HTTPException(status_code=400, detail="User is not subscribed.")

    message = messaging.Message(
        notification=messaging.Notification(
            title='YUKU Protocol Test',
            body='This is a test notification from your YUKU dashboard!',
        ),
        token=fcm_token,
    )
    
    try:
        response = messaging.send(message)
        return {"message": "Test notification sent!", "response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))