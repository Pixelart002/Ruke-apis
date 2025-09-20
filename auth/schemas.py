from pydantic import BaseModel, EmailStr, Field,field_validator
import re # Regular expressions ke liye yeh import zaroori hai





class UserCreate(BaseModel):
    fullname: str = Field(..., min_length=3, max_length=50)
    username: str


    

    email: EmailStr
    password: str = Field(..., min_length=6)
    
    # --- YEH HAI NAYA CUSTOM VALIDATOR ---

    @field_validator('username')

    @classmethod

    def validate_username(cls, value: str) -> str:

        # 1. Length check karein

        if not (3 <= len(value) <= 20):

            raise ValueError('Username must be between 3 and 20 characters long.')

        

        # 2. Pattern check karein

        if not re.match("^[a-zA-Z0-9_]+$", value):

            raise ValueError('Username can only contain letters, numbers, and underscores (_).')

        

        # Agar sab theek hai, to value return karein

        return value
    
    
    
    
    
    
    
    
    

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

# auth/schemas.py



class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(..., min_length=6)







###



# auth/schemas.py

# ... (imports)

class UserCreate(BaseModel):
    fullname: str = Field(..., min_length=3, max_length=50)
    # --- YEH LINE ADD KAREIN ---
    username: str = Field(..., min_length=3, max_length=20, regex="^[a-zA-Z0-9_]+$")
    email: EmailStr
    password: str = Field(..., min_length=6)

# ... (UserLogin model waisa hi rahega) ...

class UserInfo(BaseModel):
    # --- YEH DO LINES ADD/UPDATE KAREIN ---
    userId: str # MongoDB _id ko string format mein bhejenge
    username: str
    fullname: str
    email: EmailStr