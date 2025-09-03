# app/routes/users.py
from fastapi import APIRouter, Depends
from app.schemas import UserCreate, UserOut
from app.auth import signup

router = APIRouter(prefix="/users", tags=["users"])

@router.post("/signup", response_model=UserOut)
async def create_user(user: UserCreate):
    new_user = await signup(user)
    return new_user