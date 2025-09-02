from flask import Blueprint, request, jsonify
from database import db
from models.product import Product
from routes.user_routes import token_required, admin_required

product_bp = Blueprint('product_bp', __name__)

@product_bp.route('/products', methods=['GET'])
def list_products():
    products = Product.query.filter_by(is_active=True).all()
    return jsonify([{'product_id':p.product_id,'name':p.name,'description':p.description,'price':p.price,'stock':p.stock} for p in products])

@product_bp.route('/products', methods=['POST'])
@token_required
@admin_required
def create_product(current_user):
    data = request.json
    if not all([data.get('name'), data.get('price')]):
        return jsonify({'message':'name and price required'}),400
    product = Product(
        name=data['name'],
        description=data.get('description',''),
        price=data['price'],
        stock=data.get('stock',0)
    )
    db.session.add(product)
    db.session.commit()
    return jsonify({'message':'Product created','product_id':product.product_id})