from passlib.context import CryptContext
import uuid
from fastapi import Request
from datetime import datetime, timedelta

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def generate_token() -> str:
    return str(uuid.uuid4())

def token_expiry_datetime(days: int = 7):
    return datetime.utcnow() + timedelta(days=days)

def is_browser_safe(request: Request) -> bool:
    ua = request.headers.get("user-agent", "") or ""
    ua_l = ua.lower()
    block_keywords = ["curl", "wget", "python-requests", "scanner", "bot"]
    if any(k in ua_l for k in block_keywords):
        return False
    return True