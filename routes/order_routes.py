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
    """
    Checkout API
    --------------
    Steps:
    1. Fetch all cart items of current user.
    2. If cart empty, return error.
    3. Calculate total price.
    4. Create an Order record.
    5. Deduct stock from Products.
    6. Remove items from cart.
    7. Commit all changes.
    8. Return success response.
    """

    # Step 1: Get all cart items
    cart_items = CartItem.query.filter_by(user_id=current_user.user_id).all()

    # Step 2: If cart is empty
    if not cart_items:
        return jsonify({'message': 'Cart empty'}), 400

    # Step 3: Calculate total
    total = sum(item.quantity * item.product.price for item in cart_items)

    # Step 4: Create order
    order = Order(user_id=current_user.user_id, total=total)
    db.session.add(order)

    # Step 5 & 6: Update stock and remove items from cart
    for item in cart_items:
        item.product.stock -= item.quantity   # Reduce stock
        db.session.delete(item)               # Remove from cart (correct indentation!)

    # Step 7: Commit transaction
    db.session.commit()

    # Step 8: Return response
    return jsonify({
        'message': 'Order created successfully',
        'order_id': order.order_id,
        'total': total
    })