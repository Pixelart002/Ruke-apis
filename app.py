import os
from flask import Flask
from database import db
from routes.user_routes import user_bp
from routes.product_routes import product_bp
from routes.cart_routes import cart_bp
from routes.order_routes import order_bp
from routes.payment_routes import payment_bp
from werkzeug.security import generate_password_hash
from models.user import User

app = Flask(__name__)

DB_PATH = os.path.join(os.getcwd(), 'ruke_store.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{DB_PATH}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'ultragodmodekey'
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {"connect_args": {"check_same_thread": False}}

db.init_app(app)

with app.app_context():
    db.create_all()
    if not User.query.filter_by(is_admin=True).first():
        admin_user = User(
            username='admin',
            full_name='Super Admin',
            email='admin@example.com',
            password=generate_password_hash('admin123'),
            is_admin=True,
            phone='0000000000',
            address='Admin HQ'
        )
        db.session.add(admin_user)
        db.session.commit()
        print("Admin created: admin@example.com / admin123")

app.register_blueprint(user_bp)
app.register_blueprint(product_bp)
app.register_blueprint(cart_bp)
app.register_blueprint(order_bp)
app.register_blueprint(payment_bp)

@app.route('/health')
def health():
    return {'status':'ok'}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)