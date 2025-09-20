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
# --- YEH FUNCTION UPDATE KIYA GAYA HAI ---
def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# --- User Authentication Functions ---
def get_current_user(token: str = Depends(oauth2_scheme)):
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
    
    user = user_collection.find_one({"email": email})
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
    # For now, this is for local testing of a reset-password.html file.
    reset_link = f"https://yuku-nine.vercel.app/index .html?token={token}"

    html = f"""
    <html><body>
        <p>Hi Agent,</p>
        <p>A password reset was requested for your YUKU Protocol account.</p>
        <p>Click the link below to set a new password. This link is valid for 15 minutes.</p>
        <a href="{reset_link}" style="color: #00ff7f; text-decoration: none;">Reset Your Password</a>
        <p>If you did not request this, please disregard this email.</p>
        <p>Regards,<br>YUKU Mission Control</p>
    </body></html>
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

