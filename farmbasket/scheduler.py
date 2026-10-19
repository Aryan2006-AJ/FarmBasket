"""Background jobs.

1. Settle farmer payouts once their order is Delivered.
2. Send each farmer one digest of products that are running low.

Both can also be triggered by an admin from the Payments page.
"""
import logging

from farmbasket.extensions import db, scheduler
from farmbasket.models import FarmerPayout, Product, utcnow
from farmbasket.services.notification_service import NotificationService

logger = logging.getLogger("farmbasket.scheduler")

LOW_STOCK_THRESHOLD = 5


def process_pending_payouts():
    """Mark payouts Paid for delivered orders. Returns how many were settled."""
    settled_farmers = set()
    settled = 0
    for payout in FarmerPayout.query.filter_by(status="Pending").all():
        if payout.order and payout.order.status == "Delivered":
            payout.status = "Paid"
            payout.paid_at = utcnow()
            settled_farmers.add(payout.farmer_id)
            settled += 1
    if settled:
        db.session.commit()
        for farmer_id in settled_farmers:
            NotificationService.notify(
                farmer_id, "A payout has been settled.", category="system", link="/farmer/earnings")
    logger.info("Settled %s payout(s).", settled)
    return settled


def send_low_stock_digest():
    low = Product.query.filter(
        Product.stock <= LOW_STOCK_THRESHOLD, Product.stock > 0, Product.is_available.is_(True)).all()
    by_farmer = {}
    for p in low:
        by_farmer.setdefault(p.farmer_id, []).append(p.name)
    for farmer_id, names in by_farmer.items():
        extra = f" and {len(names) - 3} more" if len(names) > 3 else ""
        NotificationService.notify(
            farmer_id, f"Running low: {', '.join(names[:3])}{extra}.", category="stock", link="/farmer/products")
    logger.info("Low stock digest sent to %s farmer(s).", len(by_farmer))
    return len(by_farmer)


def init_scheduler(app):
    if scheduler.running:
        return

    def with_context(fn):
        def wrapper():
            with app.app_context():
                fn()
        return wrapper

    scheduler.add_job(with_context(process_pending_payouts), "interval", minutes=30,
                      id="process_payouts", replace_existing=True)
    scheduler.add_job(with_context(send_low_stock_digest), "interval", hours=12,
                      id="low_stock_digest", replace_existing=True)
    scheduler.start()
