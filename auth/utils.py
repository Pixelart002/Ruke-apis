import os
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from jose import JWTError, jwt
from dotenv import load_dotenv

load_dotenv()

# --- Password Hashing ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

# --- JWT Token Creation ---
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = os.getenv("JWT_ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = 60 # Token expires in 60 minutes

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt





# auth/utils.py (file ke neeche yeh code add karein)
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from database import user_collection

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

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




# auth/utils.py
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ... (baki code) ...

def send_password_reset_email(email: str, token: str):
    # --- .env se settings load karein ---
    sender_email = os.getenv("EMAIL_FROM")
    receiver_email = email
    password = os.getenv("SMTP_PASSWORD")
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT"))

    # --- Email ka content banayein ---
    message = MIMEMultipart("alternative")
    message["Subject"] = "YUKU Protocol: Password Reset Request"
    message["From"] = sender_email
    message["To"] = receiver_email

    # --- Reset Link (Frontend URL) ---
    # IMPORTANT: Yahan apne frontend ka URL daalein
    reset_link = f"http://127.0.0.1:5500/reset-password.html?token={token}" # Example URL

    html = f"""
    <html>
    <body>
        <p>Hi Agent,</p>
        <p>You requested a password reset for your YUKU Protocol account.</p>
        <p>Please click the link below to set a new password. This link will expire in 15 minutes.</p>
        <a href="{reset_link}">Reset Password</a>
        <p>If you did not request this, please ignore this email.</p>
        <p>Regards,<br>YUKU Mission Control</p>
    </body>
    </html>
    """

    message.attach(MIMEText(html, "html"))

    # --- Email Bhejein ---
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
