from flask import Blueprint, jsonify
from database import db
from models.cart import CartItem
from models.order import Order
from models.product import Product
from routes.user_routes import token_required

order_bp = Blueprint('order_bp', __name__)

@order_bp.route('/orders', methods=['POST'])
@token_required
def checkout(current_user):
    cart_items = CartItem.query.filter_by(user_id=current_user.user_id).all()
    if not cart_items: return jsonify({'message':'Cart empty'}),400
    total = sum([item.quantity*item.product.price for item in cart_items])
    order = Order(user_id=current_user.user_id,total=total)
    db.session.add(order)
    for item in cart_items:
      item.product.stock -= item.quantity  # reduce stock
        db.session.delete(item)  # remove from cart
    db.session.commit()
    return jsonify({'message':'Order created','order_id':order.order_id,'total':total})