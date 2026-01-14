import os
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from dotenv import load_dotenv
import urllib.parse

load_dotenv() # Load environment variables from .env file

# --- Load individual MongoDB variables ---
MONGO_USER = os.getenv("MONGO_USER")
# URL-encode the password to handle special characters
MONGO_PASSWORD = urllib.parse.quote_plus(os.getenv("MONGO_PASSWORD")) 
MONGO_CLUSTER_URL = os.getenv("MONGO_CLUSTER_URL")

# --- Build the full connection URI ---
MONGO_URI = f"mongodb+srv://{MONGO_USER}:{MONGO_PASSWORD}@{MONGO_CLUSTER_URL}/?retryWrites=true&w=majority&appName=yuku"


# --- Connect to the client ---
client = MongoClient(MONGO_URI, server_api=ServerApi('1'))

# Ping to confirm connection
try:
    client.admin.command('ping')
    print("✅ Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(f"❌ Could not connect to MongoDB: {e}")
    
db = client.yuku_protocol_db
user_collection = db["agents"]
store_collection = db["store_items"]
history_collection = db["store_history"]
settings_collection = db["store_settings"]


# --- Indexes for Speed ---
# Ensures fast sorting and searching
store_collection.create_index("name")
history_collection.create_index("inv_id", unique=True)
history_collection.create_index("date")




# new function h ye 

async def db_ping():
    # PyMongo mein ping command a-synchronous hota hai
    await client.admin.command('ping')
