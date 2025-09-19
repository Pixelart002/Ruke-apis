from pydantic import BaseModel, EmailStr, Field

class UserCreate(BaseModel):
    fullname: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class UserInfo(BaseModel):
    fullname: str
    email: EmailStr

