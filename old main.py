from fastapi import FastAPI, HTTPException, Depends, Request
from sqlalchemy.orm import Session
from database import SessionLocal, engine
from models import Base, User
from utils import hash_password, verify_password, generate_token, is_browser_safe, token_expiry_datetime
from permissions import has_permission
from ai_integration import query_ai_from_registry
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from datetime import datetime
from typing import List, Optional

Base.metadata.create_all(bind=engine)
app = FastAPI(title="Ruké Profile API")


from fastapi.middleware.cors import CORSMiddleware

# CORS settings
origins = [
    "*"  # Testing ke liye sab allow; production me apne frontend URL dalen
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)




oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.middleware("http")
async def browser_check(request: Request, call_next):
    if not is_browser_safe(request):
        raise HTTPException(status_code=403, detail="Unsafe browser detected")
    return await call_next(request)

def get_user_by_token(db: Session, token: str):
    if not token:
        return None
    return db.query(User).filter(User.session_token == token).first()

def serialize_user(u: User):
    return {
        "uid": u.uid,
        "username": u.username,
        "roles": u.roles or [],
        "is_banned": u.is_banned,
        "is_premium_user": u.is_premium_user,
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "profile_metadata": u.profile_metadata or {}
    }

# --- Signup/Login/Logout ---
@app.post("/signup")
def signup(username: str, password: str, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username exists")
    roles = ["super_admin"] if db.query(User).count() == 0 else ["user"]
    user = User(
        username=username,
        hashed_password=hash_password(password),
        is_signup=True,
        roles=roles,
        created_at=datetime.utcnow()
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"uid": user.uid, "roles": roles, "message": "User created"}

@app.post("/token")
def token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user.is_banned:
        raise HTTPException(status_code=403, detail="Banned user")
    token_val = generate_token()
    user.session_token = token_val
    user.session_expires = token_expiry_datetime()
    user.is_loggedin = True
    db.commit()
    return {"access_token": token_val, "token_type": "bearer", "roles": user.roles}

@app.post("/logout")
def logout(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    user = get_user_by_token(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")
    user.session_token = None
    user.is_loggedin = False
    db.commit()
    return {"message": "Logged out"}

# --- Profile ---
@app.get("/profile/me")
def get_profile(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    user = get_user_by_token(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")
    return user.profile_metadata or {}

@app.put("/profile/me")
def update_profile(metadata: dict, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    user = get_user_by_token(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")
    meta = user.profile_metadata or {}
    for k, v in metadata.items():
        meta[k] = v
    user.profile_metadata = meta
    db.commit()
    return {"message": "Profile updated", "profile": user.profile_metadata}

# --- Admin endpoints ---
@app.get("/admin/users")
def list_users(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    admin = get_user_by_token(db, token)
    if not admin or not has_permission(admin.roles, "manage_users"):
        raise HTTPException(status_code=403, detail="Permission denied")
    return [serialize_user(u) for u in db.query(User).all()]


@app.put("/admin/user/{uid}/ban")
def ban_user(uid: int, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    admin = get_user_by_token(db, token)
    if not admin or not has_permission(admin.roles, "ban_user"):
        raise HTTPException(status_code=403, detail="Permission denied")
    user = db.query(User).filter(User.uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_banned = True
    db.commit()
    return {"message": f"User {uid} banned"}

@app.put("/admin/user/{uid}/unban")
def unban_user(uid: int, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    admin = get_user_by_token(db, token)
    if not admin or not has_permission(admin.roles, "unban_user"):
        raise HTTPException(status_code=403, detail="Permission denied")
    user = db.query(User).filter(User.uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_banned = False
    db.commit()
    return {"message": f"User {uid} unbanned"}

@app.put("/admin/user/{uid}/roles")
def assign_roles(uid: int, roles: List[str], token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    admin = get_user_by_token(db, token)
    if not admin or not has_permission(admin.roles, "assign_roles"):
        raise HTTPException(status_code=403, detail="Permission denied")
    user = db.query(User).filter(User.uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.roles = roles
    db.commit()
    return {"message": f"Roles updated for user {uid}", "roles": roles}

# Admin: Get any user's profile
@app.get("/admin/user/{uid}/profile")
def admin_get_profile(uid: int, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    admin = get_user_by_token(db, token)
    if not admin or not has_permission(admin.roles, "edit_profile"):
        raise HTTPException(status_code=403, detail="Permission denied")
    user = db.query(User).filter(User.uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user.profile_metadata

# Admin: Update any user's profile
@app.put("/admin/user/{uid}/profile")
def admin_update_profile(uid: int, metadata: dict, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    admin = get_user_by_token(db, token)
    if not admin or not has_permission(admin.roles, "edit_profile"):
        raise HTTPException(status_code=403, detail="Permission denied")
    user = db.query(User).filter(User.uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    meta = user.profile_metadata or {}
    for k, v in metadata.items():
        meta[k] = v
    user.profile_metadata = meta
    db.commit()
    return {"message": f"Profile updated for user {uid}", "profile": user.profile_metadata}

# AI Integration Endpoint
@app.post("/ai/query")
def ai_query(tool_name: str, message: str, model: Optional[str] = None, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    user = get_user_by_token(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")
    if not has_permission(user.roles, "access_ai"):
        raise HTTPException(status_code=403, detail="Permission denied to access AI")
    result = query_ai_from_registry(tool_name=tool_name, user_message=message, model=model)
    return {"user": user.uid, "ai_response": result}

# Check current session
@app.get("/session/me")
def check_session(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    user = get_user_by_token(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")
    return {
        "uid": user.uid,
        "username": user.username,
        "roles": user.roles,
        "is_loggedin": user.is_loggedin,
        "is_banned": user.is_banned,
        "is_verified": user.is_verified,
        "is_premium_user": user.is_premium_user,
        "session_expires": user.session_expires.isoformat() if user.session_expires else None
    }

# List all roles & permissions
@app.get("/roles")
def list_roles():
    from permissions import PERMISSIONS
    return PERMISSIONS
    
    
    
    
    
    @app.get("/admin/db")
def view_db(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    admin = get_user_by_token(db, token)
    if not admin or "super_admin" not in admin.roles:
        raise HTTPException(status_code=403, detail="Permission denied")
    users = db.query(User).all()
    return [
        {
            "uid": u.uid,
            "username": u.username,
            "hashed_password": u.hashed_password,
            "session_token": u.session_token,
            "roles": u.roles,
            "is_banned": u.is_banned,
            "profile_metadata": u.profile_metadata
        }
        for u in users
    ]