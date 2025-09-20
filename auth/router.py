from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from . import schemas, utils
from database import user_collection
from datetime import timedelta, datetime, timezone

router = APIRouter(
    tags=["Authentication"]
)

@router.post("/signup")
async def create_user(user: schemas.UserCreate):
    # Yeh function bilkul sahi hai
    existing_user = user_collection.find_one({"email": user.email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Agent ID (Email) already registered."
        )
        
    hashed_password = utils.get_password_hash(user.password)
    user_data = user.dict()
    user_data["password"] = hashed_password
    user_collection.insert_one(user_data)
    
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"message": "Agent successfully authorized. Proceed to terminal access."}
    )

@router.post("/login")
async def login_for_access_token(form_data: schemas.UserLogin):
    # Find user by email
    user = user_collection.find_one({"email": form_data.email})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect Agent ID or Passcode."
        )
    
    # Verify password
    if not utils.verify_password(form_data.password, user["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect Agent ID or Passcode."
        )
        
    # --- YAHAN BADLAV KIYA GAYA HAI ---
    # Galti se paste hui function definition ko hataya gaya
    # Aur sahi function call add kiya gaya
    access_token = utils.create_access_token(data={"sub": user["email"]})
    # --- BADLAV KHATM ---
    
    # Prepare user info to return
    user_info = schemas.UserInfo(fullname=user["fullname"], email=user["email"])
    
    return JSONResponse(content={
        "token": {"access_token": access_token, "token_type": "bearer"},
        "user": user_info.dict()
    })





# auth/router.py mein yeh function daalein

@router.post("/forgot-password")
async def forgot_password(request: schemas.ForgotPasswordRequest):
    user = user_collection.find_one({"email": request.email})
    
    if not user:
        return JSONResponse(status_code=200, content={"message": "If an account with this email exists, a password reset link has been sent."})

    # --- RATE LIMIT LOGIC (3 Requests per Hour) ---
    limit_count = 3
    limit_window = timedelta(hours=1)
    current_time = datetime.now(timezone.utc)

    request_timestamps = user.get("password_reset_timestamps", [])

    recent_timestamps = [
        ts for ts in request_timestamps 
        if current_time - ts.replace(tzinfo=timezone.utc) < limit_window
    ]

    if len(recent_timestamps) >= limit_count:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"You have reached the limit of {limit_count} requests per hour. Please try again later."
        )
    # --- RATE LIMIT LOGIC END ---

    expires = timedelta(minutes=15)
    reset_token = utils.create_access_token(data={"sub": user["email"]}, expires_delta=expires)
    
    email_sent = utils.send_password_reset_email(email=request.email, token=reset_token)

    if not email_sent:
        raise HTTPException(status_code=500, detail="Failed to send password reset email.")

    recent_timestamps.append(current_time)
    user_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {"password_reset_timestamps": recent_timestamps}}
    )

    return JSONResponse(status_code=200, content={"message": "If an account with this email exists, a password reset link has been sent."})























@router.post("/reset-password")
async def reset_password(request: schemas.ResetPasswordRequest):
    # Yeh function bilkul sahi hai
    try:
        payload = utils.jwt.decode(request.token, utils.SECRET_KEY, algorithms=[utils.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=400, detail="Invalid reset token.")
    except utils.JWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token.")

    user = user_collection.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    new_hashed_password = utils.get_password_hash(request.password)
    user_collection.update_one({"email": email}, {"$set": {"password": new_hashed_password}})

    return JSONResponse(status_code=200, content={"message": "Password has been reset successfully."})

