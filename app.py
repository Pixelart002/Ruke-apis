import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from werkzeug.security import generate_password_hash, check_password_hash

# --- Configuration ---
# Replace <YOUR_PASSWORD_HERE> with your actual MongoDB Atlas password
# It's recommended to use environment variables for security in a real deployment
DB_PASSWORD = "<
9013ms@12345>" 
uri = f"mongodb+srv://kyro:{DB_PASSWORD}@kyro.ov5daxu.mongodb.net/?retryWrites=true&w=majority&appName=Kyro"

app = Flask(__name__)
CORS(app) # Enable Cross-Origin Resource Sharing

# --- Database Connection ---
try:
    client = MongoClient(uri, server_api=ServerApi('1'))
    client.admin.command('ping')
    print("✅ Successfully connected to MongoDB!")
    db = client.yuku_mission_control # Use a specific database
    users_collection = db.users      # Use a specific collection for users
except Exception as e:
    print(f"❌ Could not connect to MongoDB: {e}")
    exit()

# --- API Endpoints ---

@app.route('/signup', methods=['POST'])
def signup():
    """Handles new user registration."""
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password') or not data.get('fullname'):
        return jsonify({"error": "Missing required fields"}), 400

    fullname = data['fullname']
    email = data['email'].lower()
    password = data['password']

    # Check if user already exists
    if users_collection.find_one({'email': email}):
        return jsonify({"error": "Agent ID (Email) already registered"}), 409

    # Hash the password for security
    hashed_password = generate_password_hash(password)

    # Create user document
    user_id = users_collection.insert_one({
        'fullname': fullname,
        'email': email,
        'password': hashed_password
    }).inserted_id

    return jsonify({"message": "User registered successfully", "userId": str(user_id)}), 201

@app.route('/login', methods=['POST'])
def login():
    """Handles user login authentication."""
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({"error": "Missing email or password"}), 400

    email = data['email'].lower()
    password = data['password']

    user = users_collection.find_one({'email': email})

    if not user or not check_password_hash(user['password'], password):
        return jsonify({"error": "Invalid credentials"}), 401

    # Return user data on successful login
    return jsonify({
        "message": "Login successful",
        "user": {
            "fullname": user['fullname'],
            "email": user['email']
        }
    }), 200

# --- Main Execution ---
if __name__ == '__main__':
    app.run(debug=True, port=5000)

