# app/config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    PROJECT_NAME: str = "ruke"
    SUPABASE_URL: str = os.getenv("https://bkqiluqfdzfqdrbknaga.supabase.co")
    SUPABASE_ANON_KEY: str = os.getenv("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJrcWlsdXFmZHpmcWRyYmtuYWdhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTY4NTkyMzEsImV4cCI6MjA3MjQzNTIzMX0.jkIk-FA4k1JE83C1gVP1LaNYDg3GA2SK7fw4FB-EZIs")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "sb_secret_re8VccipFAZKflmirQEbjQ_2jZgQpiW")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60*24*7  # 7 days

settings = Settings()