from farmbasket.extensions import db
from farmbasket.models import Coupon


class CouponService:

    @staticmethod
    def get_by_code(code):
        if not code or not code.strip():
            return None
        return Coupon.query.filter_by(code=code.strip().upper()).first()

    @staticmethod
    def validate_and_price(code, order_total):
        """Returns (coupon, discount_amount, error_message)."""
        coupon = CouponService.get_by_code(code)
        if not coupon:
            return None, 0, "That coupon code is not valid."
        ok, error = coupon.is_valid_for(order_total)
        if not ok:
            return None, 0, error
        return coupon, coupon.compute_discount(order_total), None

    @staticmethod
    def mark_used(coupon):
        # The caller commits, so a coupon is only consumed if the order is saved.
        coupon.used_count = (coupon.used_count or 0) + 1

    @staticmethod
    def list_all():
        return Coupon.query.order_by(Coupon.created_at.desc()).all()

    @staticmethod
    def create(code, discount_type, discount_value, min_order_amount, max_uses):
        coupon = Coupon(
            code=code.strip().upper(), discount_type=discount_type, discount_value=discount_value,
            min_order_amount=min_order_amount or 0, max_uses=max_uses,
        )
        db.session.add(coupon)
        db.session.commit()
        return coupon

    @staticmethod
    def toggle_active(coupon):
        coupon.is_active = not coupon.is_active
        db.session.commit()
        return coupon
