from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from database import get_db
from models import User
from permissions import has_permission
from profile import get_user_by_token

router = APIRouter()

def serialize_user(u: User):
    return {
        "uid": u.uid,
        "username": u.username,
        "roles": u.roles or [],
        "is_banned": u.is_banned,
        "is_premium_user": u.is_premium_user,
        "profile_metadata": u.profile_metadata or {}
    }

@router.get("/admin/users")
def list_users(token: str = Depends(OAuth2PasswordBearer(tokenUrl="token")), db: Session = Depends(get_db)):
    admin = get_user_by_token(db, token)
    if not admin or not has_permission(admin.roles, "manage_users"):
        raise HTTPException(status_code=403, detail="Permission denied")
    return [serialize_user(u) for u in db.query(User).all()]