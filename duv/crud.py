from .models import users_col, products_col, orders_col, coupons_col
from bson import ObjectId
from passlib.hash import bcrypt

# Users
def create_user(data):
    data['password'] = bcrypt.hash(data['password'])
    return users_col.insert_one(data).inserted_id

def get_user_by_email(email):
    return users_col.find_one({"email": email})

# Products
def list_products(filter={}):
    return list(products_col.find(filter))

def add_product(data):
    return products_col.insert_one(data).inserted_id

# Orders
def create_order(order_data):
    return orders_col.insert_one(order_data).inserted_id

def list_orders(user_id):
    return list(orders_col.find({"user_id": ObjectId(user_id)}))

# Coupons
def add_coupon(data):
    return coupons_col.insert_one(data).inserted_id