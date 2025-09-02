from flask import Blueprint, request, jsonify
from database import db
from models.cart import CartItem
from models.product import Product
from routes.user_routes import token_required

cart_bp = Blueprint('cart_bp', __name__)

@cart_bp.route('/cart', methods=['POST'])
@token_required
def add_to_cart(current_user):
    data = request.json
    product_id = data.get('product_id')
    quantity = data.get('quantity',1)
    product = Product.query.get(product_id)
    if not product: return jsonify({'message':'Product not found'}),404
    if quantity>product.stock: return jsonify({'message':'Not enough stock'}),400
    cart_item = CartItem.query.filter_by(user_id=current_user.user_id,product_id=product_id).first()
    if cart_item: cart_item.quantity += quantity
    else: cart_item = CartItem(user_id=current_user.user_id, product_id=product_id, quantity=quantity); db.session.add(cart_item)
    db.session.commit()
    return jsonify({'message':'Added to cart'})