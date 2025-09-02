from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import User
from fastapi.security import OAuth2PasswordBearer

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_user_by_token(db: Session, token: str):
    if not token:
        return None
    return db.query(User).filter(User.session_token == token).first()

@router.get("/profile/me")
def get_profile(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    user = get_user_by_token(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")
    return user.profile_metadata or {}

@router.put("/profile/me")
def update_profile(metadata: dict, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    user = get_user_by_token(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")
    meta = user.profile_metadata or {}
    meta.update(metadata)
    user.profile_metadata = meta
    db.commit()
    return {"message": "Profile updated", "profile": user.profile_metadata}