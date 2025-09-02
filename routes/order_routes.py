# routes/order_routes.py
from flask import Blueprint, jsonify
from database import db
from models.cart import CartItem
from models.order import Order
from routes.user_routes import token_required

order_bp = Blueprint('order_bp', __name__, url_prefix='')

@order_bp.route('/orders', methods=['POST'])
@token_required
def checkout(current_user):
    """
    Checkout:
    - gather cart items
    - calculate total
    - create order
    - deduct stock from products
    - remove cart items
    - commit
    """
    cart_items = CartItem.query.filter_by(user_id=current_user.user_id).all()

    if not cart_items:
        return jsonify({'message': 'Cart empty'}), 400

    # Calculate total using joined product relationship
    total = sum(item.quantity * item.product.price for item in cart_items)

    order = Order(user_id=current_user.user_id, total=total)
    db.session.add(order)

    # deduct stock and clear cart
    for item in cart_items:
        # reduce stock safely
        if item.product.stock >= item.quantity:
            item.product.stock -= item.quantity
        else:
            db.session.rollback()
            return jsonify({'message': f'Not enough stock for product {item.product.product_id}'}), 400

        db.session.delete(item)

    db.session.commit()
    return jsonify({'message': 'Order created', 'order_id': order.order_id, 'total': total})