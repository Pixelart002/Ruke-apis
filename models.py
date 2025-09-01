from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON
from database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"

    uid = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_signup = Column(Boolean, default=True)
    is_loggedin = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=False)
    is_banned = Column(Boolean, default=False)
    is_premium_user = Column(Boolean, default=False)
    session_token = Column(String, unique=True, nullable=True)
    session_expires = Column(DateTime, nullable=True)
    roles = Column(JSON, default=[])
    actions = Column(JSON, default=[])
    profile_metadata = Column(JSON, default={
        "profile_picture": None,
        "cover_picture": None,
        "first_name": "",
        "middle_name": "",
        "last_name": "",
        "state": "",
        "country": "",
        "address": "",
        "pincode": "",
        "phone_number": "",
        "password_note": None
    })
    created_at = Column(DateTime, default=datetime.utcnow)