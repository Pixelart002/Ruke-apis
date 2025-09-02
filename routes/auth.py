from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm
from database import get_db
from models import User
from utils import hash_password, verify_password, generate_token, token_expiry_datetime

router = APIRouter()

@router.post("/signup")
def signup(username: str, password: str, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username exists")
    roles = ["super_admin"] if db.query(User).count() == 0 else ["user"]
    user = User(
        username=username,
        hashed_password=hash_password(password),
        is_signup=True,
        roles=roles
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"uid": user.uid, "roles": roles, "message": "User created"}

@router.post("/token")
def token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token_val = generate_token()
    user.session_token = token_val
    user.session_expires = token_expiry_datetime()
    user.is_loggedin = True
    db.commit()
    return {"access_token": token_val, "token_type": "bearer", "roles": user.roles}

@router.post("/logout")
def logout(token: str = Depends(OAuth2PasswordRequestForm), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.session_token == token).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")
    user.session_token = None
    user.is_loggedin = False
    db.commit()
    return {"message": "Logged out"}