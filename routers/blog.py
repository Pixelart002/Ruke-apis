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
MY_ADMIN_EMAIL = "9013ms@gmail.com"  # Updated with your email

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
    # Note: author_id is NOT here, so Pydantic will filter it out, preventing errors

# --- 2. SECURITY CHECK (Helper) ---
def verify_admin(current_user: dict = Depends(auth_utils.get_current_user)):
    if current_user["email"] != MY_ADMIN_EMAIL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access Denied. You are {current_user['email']}, but Owner is {MY_ADMIN_EMAIL}"
        )
    return current_user

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
    new_post["id"] = str(result.inserted_id)
    
    return new_post

# B. Read All Posts (PUBLIC) - FIXED HERE
@router.get("/", response_model=List[BlogPostResponse]) # <--- ADDED THIS LINE
async def get_all_posts(limit: int = 10):
    # 1. Fetch from DB
    posts_cursor = db.posts.find(
        {"is_published": True}
    ).sort("created_at", -1).limit(limit)
    
    posts = []
    for p in posts_cursor:
        # 2. Convert _id to string manually for Pydantic
        p["id"] = str(p["_id"])
        
        # 3. Handle potential ObjectId in author_id by filtering
        # Since we added response_model=List[BlogPostResponse], 
        # FastAPI will ignore 'author_id' (ObjectId) and only send valid JSON.
        posts.append(p)
    
    return posts

# C. Read Single Post (PUBLIC)
@router.get("/{slug}", response_model=BlogPostResponse) # <--- ADDED THIS LINE TOO
async def get_single_post(slug: str):
    post = db.posts.find_one({"slug": slug, "is_published": True})
    
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    db.posts.update_one({"_id": post["_id"]}, {"$inc": {"views": 1}})
    
    post["id"] = str(post["_id"])
    return post

# D. Delete Post (SECURE)
@router.delete("/{slug}")
async def delete_post(slug: str, admin_user: dict = Depends(verify_admin)):
    result = db.posts.delete_one({"slug": slug})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Post nahi mila")
        
    return {"message": "Post successfully deleted"}