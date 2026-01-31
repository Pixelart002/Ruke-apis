import os
from motor.motor_asyncio import AsyncIOMotorClient  # Updated import
from dotenv import load_dotenv
import urllib.parse
import asyncio

load_dotenv() # Load environment variables from .env file

# --- Load individual MongoDB variables ---
MONGO_USER = os.getenv("MONGO_USER")
# URL-encode the password to handle special characters
MONGO_PASSWORD = urllib.parse.quote_plus(os.getenv("MONGO_PASSWORD")) 
MONGO_CLUSTER_URL = os.getenv("MONGO_CLUSTER_URL")

# --- Build the full connection URI ---
MONGO_URI = f"mongodb+srv://{MONGO_USER}:{MONGO_PASSWORD}@{MONGO_CLUSTER_URL}/?retryWrites=true&w=majority&appName=yuku"


# --- Connect to the client (Async) ---
client = AsyncIOMotorClient(MONGO_URI)

db = client.yuku_protocol_db

# Collections (Yeh wahi rahenge, bas ab ink functions await maangenge)
user_collection = db["agents"]
store_collection = db["store_items"]
history_collection = db["store_history"]
settings_collection = db["store_settings"]

# --- Ping Function (Async) ---
async def db_ping():
    try:
        await client.admin.command('ping')
        print("✅ Pinged your deployment. You successfully connected to MongoDB (Async)!")
    except Exception as e:
        print(f"❌ Could not connect to MongoDB: {e}")

# Note: Motor ke saath startup par direct ping nahi kar sakte bina event loop ke.
# Isliye ping logic function mein daal diya hai.