from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from . import schemas, utils
from database import user_collection
from datetime import timedelta

router = APIRouter(
    tags=["Authentication"]
)

@router.post("/signup")
async def create_user(user: schemas.UserCreate):
    # Check if user with this email already exists
    existing_user = user_collection.find_one({"email": user.email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Agent ID (Email) already registered."
        )
        
    # Hash the password
    hashed_password = utils.get_password_hash(user.password)
    
    # Create user document
    user_data = user.dict()
    user_data["password"] = hashed_password
    
    # Insert user into the database
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
        
    # Create access token
def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

    
    # Prepare user info to return
    user_info = schemas.UserInfo(fullname=user["fullname"], email=user["email"])
    
    return JSONResponse(content={
        "token": {"access_token": access_token, "token_type": "bearer"},
        "user": user_info.dict()
    })



##pasted from here 
@router.post("/forgot-password")
async def forgot_password(request: schemas.ForgotPasswordRequest):
    user = user_collection.find_one({"email": request.email})
    if not user:
        # Hum error nahi denge taaki koi guess na kar sake ki email exist karta hai ya nahi
        return JSONResponse(status_code=200, content={"message": "If an account with this email exists, a password reset link has been sent."})

    # 15 minute ka expiry time wala token banayein
    expires = timedelta(minutes=15)
    reset_token = utils.create_access_token(data={"sub": user["email"]}, expires_delta=expires)
    
    # Email bhejne ka function call karein
    email_sent = utils.send_password_reset_email(email=request.email, token=reset_token)

    if not email_sent:
        raise HTTPException(status_code=500, detail="Failed to send password reset email.")

    return JSONResponse(status_code=200, content={"message": "If an account with this email exists, a password reset link has been sent."})


@router.post("/reset-password")
async def reset_password(request: schemas.ResetPasswordRequest):
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







