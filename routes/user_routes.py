from flask import Blueprint, request, jsonify, current_app
from database import db
from models.user import User
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from functools import wraps

user_bp = Blueprint('user_bp', __name__)

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get('Authorization','')
        token = auth.split("Bearer ")[-1] if auth.startswith("Bearer ") else auth
        if not token: return jsonify({'message':'Token missing'}),401
        try:
            data = jwt.decode(token,current_app.config['SECRET_KEY'],algorithms=["HS256"])
            kwargs['current_user'] = User.query.get(data['user_id'])
        except:
            return jsonify({'message':'Invalid token'}),401
        return f(*args,**kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args,**kwargs):
        if not kwargs['current_user'].is_admin:
            return jsonify({'message':'Admin required'}),403
        return f(*args,**kwargs)
    return decorated

@user_bp.route('/users/register', methods=['POST'])
def register_user():
    data = request.json
    required = ['username','full_name','email','password']
    if not all([data.get(x) for x in required]):
        return jsonify({'message':'username, full_name, email, password required'}),400
    if User.query.filter((User.username==data['username'])|(User.email==data['email'])).first():
        return jsonify({'message':'User exists'}),400
    user = User(
        username=data['username'],
        full_name=data['full_name'],
        email=data['email'],
        password=generate_password_hash(data['password']),
        phone=data.get('phone',''),
        address=data.get('address','')
    )
    db.session.add(user)
    db.session.commit()
    return jsonify({'message':'Registered','user_id':user.user_id}),201

@user_bp.route('/users/login', methods=['POST'])
def login_user():
    data = request.json
    user = User.query.filter_by(email=data.get('email')).first()
    if not user or not check_password_hash(user.password,data.get('password')):
        return jsonify({'message':'Invalid credentials'}),401
    token = jwt.encode({'user_id':user.user_id,'is_admin':user.is_admin},current_app.config['SECRET_KEY'],algorithm="HS256")
    return jsonify({'token':token,'is_admin':user.is_admin})