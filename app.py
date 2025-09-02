# app.py
import secrets
from flask import Flask
from database import db
from models.user import User
from models.product import Product
from models.cart import CartItem
from models.order import Order
from models.payment import Payment
from routes.user_routes import user_bp
from routes.product_routes import product_bp
from routes.cart_routes import cart_bp
from routes.order_routes import order_bp
from routes.payment_routes import payment_bp

app = Flask(__name__)

# SQLite DB path in project root
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ruke_store.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Secret (user asked no env usage)
app.config['SECRET_KEY'] = 'ultragodmodekey'

db.init_app(app)

# Register blueprints
app.register_blueprint(user_bp)
app.register_blueprint(product_bp)
app.register_blueprint(cart_bp)
app.register_blueprint(order_bp)
app.register_blueprint(payment_bp)

def create_tables_if_missing():
    """Create only missing tables so we don't attempt to recreate existing ones."""
    inspector = db.inspect(db.engine)
    existing = inspector.get_table_names()

    # mapping of table name to SQLAlchemy Table object
    mapping = {
        'users': User.__table__,
        'products': Product.__table__,
        'cart_items': CartItem.__table__,
        'orders': Order.__table__,
        'payments': Payment.__table__,
    }

    for table_name, table_obj in mapping.items():
        if table_name not in existing:
            table_obj.create(db.engine)

def ensure_admin_user():
    """Create an admin account if none exists. Generate password dynamically."""
    admin = User.query.filter_by(is_admin=True).first()
    if not admin:
        random_password = secrets.token_urlsafe(8)
        admin = User(
            username='admin',
            full_name='Administrator',
            email='admin@example.com',
            password=secrets.token_urlsafe(16)  # placeholder; we'll set hashed password below
        )
        # Use werkzeug to hash password properly
        from werkzeug.security import generate_password_hash
        admin.password = generate_password_hash(random_password)
        admin.is_admin = True
        db.session.add(admin)
        db.session.commit()
        # Print credentials to logs (visible in Koyeb logs)
        print(f"Admin created: email=admin@example.com password={random_password}")

with app.app_context():
    # create missing tables (safe)
    create_tables_if_missing()
    # ensure admin exists (generated password printed)
    ensure_admin_user()

@app.route('/health')
def health():
    return {'status': 'ok'}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)