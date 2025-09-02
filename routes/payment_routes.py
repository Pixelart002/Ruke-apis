from flask import Blueprint, request, jsonify
from database import db
from models.payment import Payment
from models.order import Order
from routes.user_routes import token_required

payment_bp = Blueprint('payment_bp', __name__)

@payment_bp.route('/payments', methods=['POST'])
@token_required
def pay_order(current_user):
    data = request.json
    order_id = data.get('order_id')
    amount = data.get('amount')

    order = Order.query.get(order_id)
    if not order or order.user_id != current_user.user_id:
        return jsonify({'message':'Invalid order'}),400

    payment = Payment(order_id=order.order_id, amount=amount, status='paid')
    order.status = 'paid'

    db.session.add(payment)
    db.session.commit()
    return jsonify({'message':'Payment successful','payment_id':payment.payment_id})