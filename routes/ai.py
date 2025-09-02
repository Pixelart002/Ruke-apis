from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import User
from permissions import has_permission
from ai_integration import query_ai_from_registry
from typing import Optional
from profile import get_user_by_token
from fastapi.security import OAuth2PasswordBearer

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

@router.post("/ai/query")
def ai_query(tool_name: str, message: str, model: Optional[str] = None, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    user = get_user_by_token(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")
    if not has_permission(user.roles, "access_ai"):
        raise HTTPException(status_code=403, detail="Permission denied to access AI")
    result = query_ai_from_registry(tool_name=tool_name, user_message=message, model=model)
    return {"user": user.uid, "ai_response": result}