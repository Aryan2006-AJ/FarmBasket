from farmbasket.extensions import db
from farmbasket.models import Order, OrderItem


class OrderRepository:

    @staticmethod
    def get_by_id(order_id):
        return db.session.get(Order, int(order_id))

    @staticmethod
    def list_by_buyer(buyer_id):
        return Order.query.filter_by(buyer_id=buyer_id).order_by(Order.created_at.desc()).all()

    @staticmethod
    def list_all():
        return Order.query.order_by(Order.created_at.desc()).all()

    @staticmethod
    def list_items_for_farmer(farmer_id):
        return OrderItem.query.filter_by(farmer_id=farmer_id).order_by(OrderItem.id.desc()).all()
