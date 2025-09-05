from pymongo import MongoClient
from pymongo.server_api import ServerApi
from bson import ObjectId
from datetime import datetime
import os

MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://kyro:<db_password>@kyro.ov5daxu.mongodb.net/?retryWrites=true&w=majority&appName=Kyro")
client = MongoClient(MONGO_URI, server_api=ServerApi('1'))
db = client['godmode_ecommerce']

# Collections
users_col = db['users']
products_col = db['products']
orders_col = db['orders']
coupons_col = db['coupons']