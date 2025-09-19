# routers/users.py

from fastapi import APIRouter, Depends
from auth import utils as auth_utils, schemas as auth_schemas
from typing import Dict

router = APIRouter(
    prefix="/users",
    tags=["Users"]
)

@router.get("/me", response_model=auth_schemas.UserInfo)
async def read_users_me(current_user: Dict = Depends(auth_utils.get_current_user)):
    # The dependency get_current_user already fetches the user from the DB
    # We just need to return it.
    return current_user
