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
# Yahan apna email likho. Sirf ye email wala banda hi post daal payega.
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
    """
    Ye function gatekeeper hai. 
    Agar email match nahi hua toh error fek dega.
    """
    if current_user["email"] != MY_ADMIN_EMAIL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sirf Owner hi post upload kar sakta hai."
        )
    return current_user

# --- 3. ENDPOINTS ---

# A. Create Post (SECURE - Sirf Aap)
@router.post("/create", response_model=BlogPostResponse)
async def create_post(
    post: BlogPostCreate,
    admin_user: dict = Depends(verify_admin) # <-- Ye check karega ki aap hi ho
):
    # 1. Slug banao (URL ke liye)
    slug = slugify(post.title)
    
    # Check duplicate slug
    if db.posts.find_one({"slug": slug}):
        slug = f"{slug}-{int(datetime.now().timestamp())}"

    # 2. Data Prepare karo
    new_post = post.dict()
    new_post.update({
        "slug": slug,
        "author_id": admin_user["_id"],
        "author_name": admin_user["fullname"],
        "created_at": datetime.now(),
        "views": 0
    })

    # 3. Save karo
    result = db.posts.insert_one(new_post)
    new_post["id"] = str(result.inserted_id)
    
    return new_post

# B. Read All Posts (PUBLIC - Koi bhi dekh sakta hai)
@router.get("/")
async def get_all_posts(limit: int = 10):
    posts_cursor = db.posts.find(
        {"is_published": True}
    ).sort("created_at", -1).limit(limit)
    
    posts = []
    for p in posts_cursor:
        p["id"] = str(p["_id"])
        posts.append(p)
    
    return posts

# C. Read Single Post (PUBLIC)
@router.get("/{slug}")
async def get_single_post(slug: str):
    # 1. Post dhundo
    post = db.posts.find_one({"slug": slug, "is_published": True})
    
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # 2. Views badhao (Optional)
    db.posts.update_one({"_id": post["_id"]}, {"$inc": {"views": 1}})
    
    post["id"] = str(post["_id"])
    return post

# D. Delete Post (SECURE - Sirf Aap)
@router.delete("/{slug}")
async def delete_post(slug: str, admin_user: dict = Depends(verify_admin)):
    result = db.posts.delete_one({"slug": slug})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Post nahi mila")
        
    return {"message": "Post successfully delete ho gaya"}