from pydantic import BaseModel, EmailStr, Field,field_validator
import re # Regular expressions ke liye yeh import zaroori hai





class UserCreate(BaseModel):
    fullname: str = Field(..., min_length=3, max_length=50)
    username: str = Field(..., min_length=3, max_length=20, pattern="^[a-zA-Z0-9_]+$")
    



    

    email: EmailStr
    password: str = Field(..., min_length=6)
    

    
    
    
    
    
    

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class UserInfo(BaseModel):
    userId: str # MongoDB _id ko string format mein bhejenge
    username: str
    fullname: str
    email: EmailStr



class UserUpdate(BaseModel):
    fullname: str = Field(..., min_length=3, max_length=50)
    username: str = Field(..., min_length=3, max_length=20, pattern="^[a-zA-Z0-9_]+$")





class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(..., min_length=6)










