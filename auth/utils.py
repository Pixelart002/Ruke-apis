import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from database import user_collection

load_dotenv()

# --- Security & JWT Configuration ---
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = os.getenv("JWT_ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = 60
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


# --- Password Hashing Functions ---
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)


# --- JWT Token Creation ---
def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# --- User Authentication Functions (UPDATED FOR ASYNC) ---
# 1. 'async' keyword lagaya gaya
async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    # 2. 'await' keyword lagaya gaya (Motor ke liye zaroori)
    user = await user_collection.find_one({"email": email})
    
    if user is None:
        raise credentials_exception
    return user


# --- Email Sending Function ---
def send_password_reset_email(email: str, token: str):
    sender_email = os.getenv("EMAIL_FROM")
    receiver_email = email
    password = os.getenv("SMTP_PASSWORD")
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT"))

    message = MIMEMultipart("alternative")
    message["Subject"] = "YUKU Protocol: Password Reset Request"
    message["From"] = sender_email
    message["To"] = receiver_email

    # IMPORTANT: Update this URL to your frontend's deployed URL when you go live.
    reset_link = f"https://yuku-nine.vercel.app/reset-password.html?token={token}"

    html = f"""
   <html>
  <body style="margin:0; padding:40px 0; font-family: Arial, Helvetica, sans-serif; background:#f5f6f7; color:#202124; text-align:center;">
    
    <div style="max-width:600px; margin:auto; background:#ffffff; border-radius:8px; padding:40px; box-shadow:0 2px 8px rgba(0,0,0,0.05); text-align:left;">
      
      <div style="text-align:center; margin-bottom:25px;">
        <img src="https://media.giphy.com/media/26tn33aiTi1jkl6H6/giphy.gif" 
             alt="YUKU Security Animation" 
             width="80" height="80" 
             style="border-radius:50%; display:block; margin:auto;">
      </div>
      
      <h2 style="margin:0 0 30px; font-size:22px; font-weight:600; color:#202124; text-align:center;">
        YUKU Protocol Security
      </h2>
      
      <p style="font-size:16px; line-height:1.6; margin:0 0 20px;">Hi Agent,</p>
      
      <p style="font-size:16px; line-height:1.6; margin:0 0 20px;">
        A password reset was requested for your <strong>YUKU Protocol</strong> account.
      </p>
      
      <p style="font-size:16px; line-height:1.6; margin:0 0 30px;">
        Click the button below to set a new password. This link is valid for <strong>15 minutes</strong>.
      </p>
      
      <p style="text-align:center; margin:0 0 30px;">
        <a href="{reset_link}" 
           style="background:#1a73e8; color:#ffffff; text-decoration:none; padding:14px 28px; border-radius:4px; font-weight:600; font-size:15px; display:inline-block;">
           Reset Your Password
        </a>
      </p>
      
      <p style="font-size:14px; line-height:1.6; color:#5f6368; margin:0 0 20px;">
        If you did not request this, you can safely ignore this email.
      </p>
      
      <p style="font-size:14px; line-height:1.6; margin:0;">
        Regards,<br>
        <strong>YUKU Mission Control</strong>
      </p>
    </div>
    
    <p style="margin-top:20px; font-size:12px; color:#9aa0a6;">
      © 2025 YUKU Protocol. All rights reserved.
    </p>
  </body>
</html>
    """
    message.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(os.getenv("SMTP_USER"), password)
            server.sendmail(sender_email, receiver_email, message.as_string())
        print("Password reset email sent successfully!")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False