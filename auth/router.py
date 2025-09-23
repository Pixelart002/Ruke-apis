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
        # --- USERNAME UNIQUENESS CHECK ADD KAREIN ---
    if user_collection.find_one({"username": user.username}):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This username is already taken. Please choose another one."
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
    user_info = schemas.UserInfo(
        userId=str(user["_id"]), # _id ko string mein convert karein
        username=user.get("username","N/A"),
        fullname=user["fullname"],
        email=user["email"]
    )
    
    return JSONResponse(content={
        "token": {"access_token": access_token, "token_type": "bearer"},
        "user": user_info.dict()
    })






























@router.post("/reset-password")

async def reset_password(request: schemas.ResetPasswordRequest):

    try:

        # Decode the token to get the email and the token version

        payload = jwt.decode(

            request.token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]

        )

        email: str = payload.get("sub")

        token_version: int = payload.get("prv") # Get Password Reset Version



        if email is None or token_version is None:

            raise HTTPException(

                status_code=status.HTTP_401_UNAUTHORIZED,

                detail="Invalid token claims."

            )



    except jwt.ExpiredSignatureError:

        raise HTTPException(

            status_code=status.HTTP_401_UNAUTHORIZED,

            detail="Reset link has expired."

        )

    except jwt.PyJWTError:

        raise HTTPException(

            status_code=status.HTTP_401_UNAUTHORIZED,

            detail="Invalid or expired reset link."

        )



    # Find the user in the database

    user = user_collection.find_one({"email": email})



    # SECURITY CHECK 1: Validate the token version

    # If user doesn't exist or token version doesn't match, the link is invalid.

    # This instantly expires old links when a new one is requested.

    if not user or user.get("password_reset_version") != token_version:

        raise HTTPException(

            status_code=status.HTTP_401_UNAUTHORIZED,

            detail="Invalid or expired reset link."

        )

        

    # SECURITY CHECK 2: Prevent reusing the old password

    if utils.verify_password(request.password, user["hashed_password"]):

        raise HTTPException(

            status_code=status.HTTP_400_BAD_REQUEST,

            detail="New passcode cannot be the same as the old one."

        )



    # Hash the new password

    new_hashed_password = utils.get_password_hash(request.password)

    

    # SECURITY CHECK 3: Invalidate the token immediately after use

    # Increment the version number so this token can never be used again.

    current_token_version = user.get("password_reset_version", 0)

    

    user_collection.update_one(

        {"_id": user["_id"]},

        {

            "$set": {

                "hashed_password": new_hashed_password,

                "password_reset_version": current_token_version + 1

            }

        }

    )



    return JSONResponse(

        status_code=status.HTTP_200_OK, 

        content={"message": "Passcode has been updated successfully."}

    )









@router.post("/reset-password")
async def reset_password(request: schemas.ResetPasswordRequest):
    # Yeh function bilkul sahi hai
    try:
        payload = utils.jwt.decode(request.token, utils.SECRET_KEY, algorithms=[utils.ALGORITHM])
        email: str = payload.get("sub")
        token_version: int = payload.get("prv")

      
        if email is None:
            raise HTTPException(status_code=400, detail="Invalid reset token.")
    except utils.JWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token.")

    user = user_collection.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    # --- NAYA SECURITY CHECK ---
    # Check karein ki token ka version database ke version se match karta hai ya nahi
    db_token_version = user.get("password_reset_version", 0)
    if token_version != db_token_version:
        raise HTTPException(status_code=400, detail="This reset link has expired because a newer one was requested.")
    # --- CHECK KHATM ---

    new_hashed_password = utils.get_password_hash(request.password)
    # Token ko dobara istemaal hone se rokne ke liye version ko firse badha dein
    user_collection.update_one(
        {"email": email}, 
        {"$set": {"password": new_hashed_password}, "$inc": {"password_reset_version": 1}}
    )

    return JSONResponse(status_code=200, content={"message": "Password has been reset successfully."})