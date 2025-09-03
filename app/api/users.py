from fastapi import APIRouter, Depends
from app.api.deps import get_current_user, get_admin_user

router = APIRouter()

@router.get("/me")
def me(user=Depends(get_current_user)):
    return {"id": user["id"], "email": user["email"], "username": user.get("username"), "is_admin": user.get("is_admin", False)}

@router.get("/list")
def list_users(admin=Depends(get_admin_user)):
    client = admin and __import__('app').db.supabase.get_client()  # fallback safe call removed in packaged usage
    # Instead, prefer using get_client directly
    from app.db.supabase import get_client
    res = get_client().table("users").select("id, username, email, is_admin, created_at").order("created_at", desc=True).execute()
    return res.data
