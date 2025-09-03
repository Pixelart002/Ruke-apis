# app/auth.py
from fastapi import HTTPException, status, Depends
from app.schemas import UserCreate, Token
from app.utils.security import hash_password, verify_password, create_access_token
from app.database import insert_user, get_user_by_email
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

async def signup(user: UserCreate):
    existing_user = get_user_by_email(user.email)
    if existing_user.data and len(existing_user.data) > 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    password_hash = hash_password(user.password)
    response = insert_user(user.username, user.email, password_hash)
    return response.data[0]

async def login(form_data: OAuth2PasswordRequestForm):
    user_resp = get_user_by_email(form_data.username)
    if not user_resp.data or len(user_resp.data) == 0:
        raise HTTPException(status_code=400, detail="Invalid credentials")
    user = user_resp.data[0]
    if not verify_password(form_data.password, user["password"]):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    token = create_access_token({"user_id": user["id"]})
    return {"access_token": token, "token_type": "bearer"}