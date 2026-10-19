from collections import defaultdict
from datetime import timedelta

from farmbasket.extensions import db
from farmbasket.models import (
    CartItem, Order, OrderItem, Payment, FarmerPayout, User, PROGRESS, utcnow,
)
from farmbasket.services.cart_service import CartService
from farmbasket.services.coupon_service import CouponService
from farmbasket.services.loyalty_service import LoyaltyService
from farmbasket.services.notification_service import NotificationService
from farmbasket.services.email_service import EmailService
from farmbasket.utils import generate_order_number, generate_transaction_ref

LOW_STOCK_THRESHOLD = 5


def rollup_order_status(order):
    """An order is only as far along as its slowest active item."""
    active = [i for i in order.items if i.status != "Cancelled"]
    if not active:
        order.status = "Cancelled"
    else:
        order.status = min(active, key=lambda i: PROGRESS.index(i.status)).status
    return order.status


class OrderService:

    @staticmethod
    def place_order(buyer_id, form, coupon_code=None, redeem_points=0):
        """Create an order from the buyer's cart in one transaction.
        Returns (order, error_message)."""
        buyer = db.session.get(User, buyer_id)
        cart_items = CartService.get_cart_items(buyer_id)
        if not cart_items:
            return None, "Your cart is empty."

        blocked = CartService.undeliverable_items(buyer, cart_items)
        if blocked:
            names = ", ".join(i.product.name for i in blocked)
            return None, f"Not deliverable to your area: {names}. Remove these items to continue."

        for item in cart_items:
            if not item.product.in_stock or item.quantity > item.product.stock:
                return None, f"Not enough stock left for {item.product.name}."

        subtotal = round(sum(i.subtotal for i in cart_items), 2)

        coupon, coupon_discount = None, 0
        if coupon_code and coupon_code.strip():
            coupon, coupon_discount, error = CouponService.validate_and_price(coupon_code, subtotal)
            if error:
                return None, error

        redeem_points = max(0, int(redeem_points or 0))
        redeem_points = min(redeem_points, LoyaltyService.max_redeemable_points(buyer, subtotal - coupon_discount))
        points_discount = redeem_points * LoyaltyService.point_value_rupees()
        total_amount = round(max(0.0, subtotal - coupon_discount - points_discount), 2)

        method = form.payment_method.data
        try:
            order = Order(
                buyer_id=buyer_id, locality_id=buyer.locality_id,
                order_number=generate_order_number(), total_amount=total_amount, status="Confirmed",
                delivery_name=form.delivery_name.data.strip(), delivery_phone=form.delivery_phone.data.strip(),
                delivery_address=form.delivery_address.data.strip(), delivery_city=form.delivery_city.data.strip(),
                delivery_pincode=form.delivery_pincode.data.strip(), delivery_slot=form.delivery_slot.data,
                payment_method=method, payment_status="Pending" if method == "COD" else "Paid",
                coupon_code=coupon.code if coupon else None,
                discount_amount=round(coupon_discount + points_discount, 2), points_redeemed=redeem_points,
            )
            db.session.add(order)
            db.session.flush()

            farmers, low_stock = set(), []
            for item in cart_items:
                product = item.product
                product.stock -= item.quantity
                if 0 < product.stock <= LOW_STOCK_THRESHOLD:
                    low_stock.append(product)
                db.session.add(OrderItem(
                    order_id=order.id, product_id=product.id, farmer_id=product.farmer_id,
                    product_name=product.name, price=product.price, quantity=item.quantity,
                    subtotal=item.subtotal, status="Confirmed"))
                db.session.add(FarmerPayout(
                    farmer_id=product.farmer_id, order_id=order.id, amount=item.subtotal, status="Pending"))
                farmers.add(product.farmer_id)

            db.session.add(Payment(
                order_id=order.id, amount=total_amount, method=method, status=order.payment_status,
                transaction_ref=generate_transaction_ref()))

            if redeem_points:
                LoyaltyService.redeem(buyer, redeem_points, order.id)
            order.points_earned = LoyaltyService.earn(buyer, total_amount, order.id)
            if coupon:
                CouponService.mark_used(coupon)

            CartItem.query.filter_by(buyer_id=buyer_id).delete()
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        for farmer_id in farmers:
            NotificationService.notify(
                farmer_id, f"New order {order.order_number} for {order.delivery_slot}.",
                category="order", link="/farmer/orders")
        for product in low_stock:
            NotificationService.notify(
                product.farmer_id, f"Low stock: {product.name} has {product.stock} {product.unit} left.",
                category="stock", link="/farmer/products")
        NotificationService.notify(
            buyer_id, f"Order {order.order_number} is confirmed.", category="order",
            link=f"/buyer/orders/{order.id}")
        EmailService.order_confirmation_email(order)
        return order, None

    @staticmethod
    def advance_item(item):
        """Move one order item to the next step. Returns (ok, message)."""
        if item.status == "Cancelled":
            return False, "This item was cancelled."
        if item.status == "Delivered":
            return False, "This item is already delivered."

        item.status = PROGRESS[PROGRESS.index(item.status) + 1]
        order = item.order
        before = order.status
        rollup_order_status(order)

        if order.status == "Delivered" and order.payment_method == "COD":
            order.payment_status = "Paid"
            for payment in order.payments:
                payment.status = "Paid"
        db.session.commit()

        if order.status != before:
            NotificationService.notify(
                order.buyer_id, f"Order {order.order_number} is now {order.status}.",
                category="order", link=f"/buyer/orders/{order.id}")
            EmailService.order_status_email(order)
        return True, f"Marked as {item.status}."

    @staticmethod
    def cancel_order(order):
        """Cancel before anything leaves the farm. Returns (ok, error)."""
        if order.status == "Cancelled":
            return False, "This order is already cancelled."
        if any(i.status in ("Out for Delivery", "Delivered") for i in order.items):
            return False, "This order is already out for delivery and can no longer be cancelled."

        for item in order.items:
            item.product.stock += item.quantity
            item.status = "Cancelled"
        for payout in order.payouts:
            if payout.status == "Pending":
                payout.status = "Cancelled"
        LoyaltyService.reverse_for_cancelled_order(order.buyer, order)

        order.status = "Cancelled"
        order.payment_status = "Refunded" if order.payment_status == "Paid" else "Cancelled"
        for payment in order.payments:
            payment.status = order.payment_status
        db.session.commit()

        NotificationService.notify(
            order.buyer_id, f"Order {order.order_number} was cancelled.", category="order",
            link=f"/buyer/orders/{order.id}")
        for farmer_id in {i.farmer_id for i in order.items}:
            NotificationService.notify(
                farmer_id, f"Order {order.order_number} was cancelled by the buyer.", category="order",
                link="/farmer/orders")
        return True, None

    @staticmethod
    def farmer_stats(farmer_id):
        items = OrderItem.query.filter_by(farmer_id=farmer_id).all()
        active = [i for i in items if i.status != "Cancelled"]
        payouts = FarmerPayout.query.filter_by(farmer_id=farmer_id).all()
        return {
            "total_orders": len({i.order_id for i in active}),
            "total_sales": round(sum(i.subtotal for i in active), 2),
            "pending_orders": len({i.order_id for i in active if i.status != "Delivered"}),
            "paid_earnings": round(sum(p.amount for p in payouts if p.status == "Paid"), 2),
            "pending_earnings": round(sum(p.amount for p in payouts if p.status == "Pending"), 2),
        }

    @staticmethod
    def revenue_trend(days=14):
        buckets = defaultdict(float)
        for o in Order.query.filter(Order.status != "Cancelled").all():
            buckets[o.created_at.strftime("%Y-%m-%d")] += o.total_amount
        today = utcnow().date()
        series = []
        for i in range(days - 1, -1, -1):
            d = today - timedelta(days=i)
            series.append((d.strftime("%d %b"), round(buckets.get(d.strftime("%Y-%m-%d"), 0), 2)))
        return series
