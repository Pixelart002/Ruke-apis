from fastapi import APIRouter, HTTPException, status, Depends
from app.models.schemas import UserCreate, Token
from app.db.supabase import get_client
from app.core.security import hash_password, verify_password, create_token
from pydantic import EmailStr
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from app.models.schemas import UserOut
from typing import Dict

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

@router.post("/signup", response_model=UserOut)
def signup(payload: UserCreate):
    client = get_client()
    # check existing
    q = client.table("users").select("*").eq("email", payload.email).execute()
    if q.data and len(q.data) > 0:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed = hash_password(payload.password)
    user = {"username": payload.username, "email": payload.email, "password": hashed, "is_admin": False}
    ins = client.table("users").insert(user).execute()
    if ins.error:
        raise HTTPException(status_code=500, detail="Could not create user")
    data = ins.data[0]
    return {"id": data["id"], "username": data["username"], "email": data["email"], "is_admin": data.get("is_admin", False)}

@router.post("/token", response_model=Token)
def token(form_data: OAuth2PasswordRequestForm = Depends()):
    client = get_client()
    res = client.table("users").select("*").eq("email", form_data.username).execute()
    if not res.data or len(res.data) == 0:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    user = res.data[0]
    if not verify_password(form_data.password, user["password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    access = create_token(str(user["id"]))
    return {"access_token": access, "token_type": "bearer"}
