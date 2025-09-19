from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from . import schemas, utils
from database import user_collection

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
    access_token = utils.create_access_token(
        data={"sub": user["email"]}
    )
    
    # Prepare user info to return
    user_info = schemas.UserInfo(fullname=user["fullname"], email=user["email"])
    
    return JSONResponse(content={
        "token": {"access_token": access_token, "token_type": "bearer"},
        "user": user_info.dict()
    })

