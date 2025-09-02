# app.py

from flask import Flask
from database import db
from models.user import User
from models.cart import CartItem
from models.order import Order
from models.product import Product
from routes.user_routes import user_bp
from routes.order_routes import order_bp

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db.init_app(app)

# Register Blueprints
app.register_blueprint(user_bp)
app.register_blueprint(order_bp)

def create_tables_if_not_exist():
    """Create tables only if they do not exist (safe for production)."""
    inspector = db.inspect(db.engine)
    existing_tables = inspector.get_table_names()

    if "users" not in existing_tables:
        User.__table__.create(db.engine)
    if "cart_item" not in existing_tables:
        CartItem.__table__.create(db.engine)
    if "orders" not in existing_tables:
        Order.__table__.create(db.engine)
    if "product" not in existing_tables:
        Product.__table__.create(db.engine)

# Create tables safely inside app context
with app.app_context():
    create_tables_if_not_exist()

if __name__ == "__main__":
    # For local testing
    app.run(debug=True)