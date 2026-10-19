from flask import current_app

from farmbasket.extensions import db
from farmbasket.models import PointsTransaction


class LoyaltyService:
    """Points are changed in the caller's transaction; the caller commits."""

    @staticmethod
    def points_earned_for_amount(amount):
        per_100 = current_app.config.get("LOYALTY_POINTS_PER_100_RUPEES", 1)
        return int((amount // 100) * per_100)

    @staticmethod
    def point_value_rupees():
        return current_app.config.get("LOYALTY_POINT_VALUE_RUPEES", 1)

    @staticmethod
    def max_redeemable_points(user, order_total):
        """Up to half of an order can be paid with points, never more than the balance."""
        cap_by_order = int((max(order_total, 0) * 0.5) // LoyaltyService.point_value_rupees())
        return max(0, min(user.loyalty_points or 0, cap_by_order))

    @staticmethod
    def redeem(user, points, order_id):
        points = min(max(points, 0), user.loyalty_points or 0)
        if points:
            user.loyalty_points -= points
            db.session.add(PointsTransaction(
                user_id=user.id, order_id=order_id, points=-points, reason="Redeemed at checkout"))
        return points

    @staticmethod
    def earn(user, amount, order_id):
        points = LoyaltyService.points_earned_for_amount(amount)
        if points:
            user.loyalty_points = (user.loyalty_points or 0) + points
            db.session.add(PointsTransaction(
                user_id=user.id, order_id=order_id, points=points, reason="Earned on order"))
        return points

    @staticmethod
    def reverse_for_cancelled_order(user, order):
        if order.points_redeemed:
            user.loyalty_points = (user.loyalty_points or 0) + order.points_redeemed
            db.session.add(PointsTransaction(
                user_id=user.id, order_id=order.id, points=order.points_redeemed,
                reason="Points returned, order cancelled"))
        if order.points_earned:
            removed = min(order.points_earned, user.loyalty_points or 0)
            user.loyalty_points = (user.loyalty_points or 0) - removed
            db.session.add(PointsTransaction(
                user_id=user.id, order_id=order.id, points=-removed,
                reason="Points removed, order cancelled"))

    @staticmethod
    def history(user_id):
        return (PointsTransaction.query.filter_by(user_id=user_id)
                .order_by(PointsTransaction.created_at.desc()).all())
