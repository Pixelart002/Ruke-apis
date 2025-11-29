from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from slugify import slugify
from bson import ObjectId

# Aapke existing modules
from database import db
from auth import utils as auth_utils

router = APIRouter(prefix="/blog", tags=["Personal Blog"])

# --- CONFIGURATION ---
MY_ADMIN_EMAIL = "9013ms@gmail.com"

# --- 1. SCHEMAS (Data Models) ---
class BlogPostCreate(BaseModel):
    title: str = Field(..., min_length=5)
    content: str = Field(..., description="Markdown or HTML content")
    tags: List[str] = []
    cover_image: Optional[str] = None
    is_published: bool = True

class BlogPostResponse(BlogPostCreate):
    id: str
    slug: str
    created_at: datetime
    views: int

# --- 2. SECURITY CHECK (Helper) ---
def verify_admin(current_user: dict = Depends(auth_utils.get_current_user)):
    if current_user["email"] != MY_ADMIN_EMAIL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access Denied. You are {current_user['email']}, but Owner is {MY_ADMIN_EMAIL}"
        )
    return current_user

# --- HELPER FUNCTION TO FIX MONGODB OBJECTID ---
def fix_post_id(post_doc):
    """
    This function manually converts ObjectId to string
    and removes the original _id field to prevent crashes.
    """
    if not post_doc:
        return None
        
    # 1. Convert _id to string 'id'
    post_doc["id"] = str(post_doc["_id"])
    
    # 2. DELETE the original _id (ObjectId) so FastAPI doesn't choke on it
    del post_doc["_id"]
    
    # 3. Handle author_id if it exists (Convert to string)
    if "author_id" in post_doc:
        post_doc["author_id"] = str(post_doc["author_id"])
        
    return post_doc

# --- 3. ENDPOINTS ---

# A. Create Post (SECURE)
@router.post("/create", response_model=BlogPostResponse)
async def create_post(
    post: BlogPostCreate,
    admin_user: dict = Depends(verify_admin)
):
    slug = slugify(post.title)
    if db.posts.find_one({"slug": slug}):
        slug = f"{slug}-{int(datetime.now().timestamp())}"

    new_post = post.dict()
    new_post.update({
        "slug": slug,
        "author_id": admin_user["_id"], # Saves as ObjectId
        "author_name": admin_user["fullname"],
        "created_at": datetime.now(),
        "views": 0
    })

    result = db.posts.insert_one(new_post)
    
    # Fetch the inserted document and fix ID
    created_post = db.posts.find_one({"_id": result.inserted_id})
    return fix_post_id(created_post)

# B. Read All Posts (PUBLIC)
@router.get("/", response_model=List[BlogPostResponse])
async def get_all_posts(limit: int = 10):
    posts_cursor = db.posts.find(
        {"is_published": True}
    ).sort("created_at", -1).limit(limit)
    
    clean_posts = []
    for p in posts_cursor:
        # Use helper to clean ObjectId
        clean_posts.append(fix_post_id(p))
    
    return clean_posts

# C. Read Single Post (PUBLIC)
@router.get("/{slug}", response_model=BlogPostResponse)
async def get_single_post(slug: str):
    post = db.posts.find_one({"slug": slug, "is_published": True})
    
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    db.posts.update_one({"_id": post["_id"]}, {"$inc": {"views": 1}})
    
    # Use helper to clean ObjectId
    return fix_post_id(post)

# D. Delete Post (SECURE)
@router.delete("/{slug}")
async def delete_post(slug: str, admin_user: dict = Depends(verify_admin)):
    result = db.posts.delete_one({"slug": slug})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Post nahi mila")
        
    return {"message": "Post successfully deleted"}