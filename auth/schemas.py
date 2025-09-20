from pydantic import BaseModel, EmailStr, Field

class UserCreate(BaseModel):
    fullname: str = Field(..., min_length=3, max_length=50)
    username: str = Field(..., min_length=3, max_length=20, regex="^[a-zA-Z0-9_]+$")
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