# /Ruke-apis/database.py

import os
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from dotenv import load_dotenv
from urllib.parse import quote_plus # <-- Import this

load_dotenv()

# Get database credentials from environment variables
MONGO_USER = os.getenv("MONGO_USER")
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD")
MONGO_CLUSTER_URL = os.getenv("MONGO_CLUSTER_URL") # e.g., kyro.ov5daxu.mongodb.net

# Escape the username and password
escaped_user = quote_plus(MONGO_USER)
escaped_password = quote_plus(MONGO_PASSWORD)

# Build the final, safe MongoDB URI
MONGO_URI = f"mongodb+srv://{escaped_user}:{escaped_password}@{MONGO_CLUSTER_URL}/?retryWrites=true&w=majority&appName=yuku"

client = MongoClient(MONGO_URI, server_api=ServerApi('1'))

# Ping to confirm connection
try:
    client.admin.command('ping')
    print("✅ Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(f"❌ Could not connect to MongoDB: {e}")
    
db = client.yuku_protocol_db
user_collection = db["agents"]
