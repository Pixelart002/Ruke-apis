# app/database.py
from app.utils.supabase_client import supabase

# Helper functions to interact with Supabase tables

def insert_user(username: str, email: str, password_hash: str):
    return supabase.table("users").insert({
        "username": username,
        "email": email,
        "password": password_hash
    }).execute()

def get_user_by_email(email: str):
    return supabase.table("users").select("*").eq("email", email).execute()

def insert_product(title, description, price, image_url):
    return supabase.table("products").insert({
        "title": title,
        "description": description,
        "price": price,
        "image_url": image_url
    }).execute()

def get_products():
    return supabase.table("products").select("*").execute()