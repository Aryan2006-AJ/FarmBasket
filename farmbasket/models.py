import secrets
from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from farmbasket.extensions import db


def utcnow():
    """Naive UTC timestamp (SQLite stores naive datetimes)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


ROLE_BUYER = "buyer"
ROLE_FARMER = "farmer"
ROLE_ADMIN = "admin"

# An order moves forward through PROGRESS one step at a time.
# "Cancelled" is reached only through the buyer cancellation flow.
PROGRESS = ["Confirmed", "Packed", "Out for Delivery", "Delivered"]
ORDER_STATUSES = PROGRESS + ["Cancelled"]
PAYMENT_STATUSES = ["Pending", "Paid", "Failed", "Refunded", "Cancelled"]
PAYOUT_STATUSES = ["Pending", "Paid", "Cancelled"]

KYC_NOT_SUBMITTED = "Not Submitted"
KYC_PENDING = "Pending"
KYC_APPROVED = "Approved"
KYC_REJECTED = "Rejected"

PRODUCT_CATEGORIES = ["Vegetables", "Fruits", "Grains", "Dairy", "Spices", "Other"]


class Locality(db.Model):
    """A serviceable area. Farmers deliver inside their own locality and
    buyers only order from farmers in theirs."""
    __tablename__ = "localities"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    city = db.Column(db.String(80), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    __table_args__ = (db.UniqueConstraint("name", "city", name="uq_locality_name_city"),)

    @property
    def label(self):
        return f"{self.name}, {self.city}"

    def __repr__(self):
        return f"<Locality {self.label}>"


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=ROLE_BUYER)
    phone = db.Column(db.String(20))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    terms_accepted_at = db.Column(db.DateTime, nullable=True)

    locality_id = db.Column(db.Integer, db.ForeignKey("localities.id"), nullable=True, index=True)
    locality = db.relationship("Locality", backref="users", foreign_keys=[locality_id])

    api_key = db.Column(db.String(64), unique=True, nullable=True, index=True)

    totp_secret = db.Column(db.String(32), nullable=True)
    totp_enabled = db.Column(db.Boolean, default=False)

    kyc_status = db.Column(db.String(20), default=KYC_NOT_SUBMITTED)
    kyc_document = db.Column(db.String(255), nullable=True)
    kyc_submitted_at = db.Column(db.DateTime, nullable=True)
    kyc_reviewed_at = db.Column(db.DateTime, nullable=True)
    kyc_notes = db.Column(db.String(255), nullable=True)

    loyalty_points = db.Column(db.Integer, default=0)

    products = db.relationship("Product", backref="farmer", lazy=True, foreign_keys="Product.farmer_id")
    cart_items = db.relationship("CartItem", backref="buyer", lazy=True, foreign_keys="CartItem.buyer_id")
    orders = db.relationship("Order", backref="buyer", lazy=True, foreign_keys="Order.buyer_id")
    wishlist_items = db.relationship("Wishlist", backref="buyer", lazy=True, foreign_keys="Wishlist.buyer_id")
    reviews = db.relationship("Review", backref="buyer", lazy=True, foreign_keys="Review.buyer_id")
    payouts = db.relationship("FarmerPayout", backref="farmer", lazy=True, foreign_keys="FarmerPayout.farmer_id")

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    def generate_api_key(self):
        self.api_key = secrets.token_hex(24)
        return self.api_key

    @property
    def display_id(self):
        prefix = {"buyer": "BUY", "farmer": "FRM", "admin": "ADM"}.get(self.role, "USR")
        return f"{prefix}-{self.id:04d}"

    @property
    def is_verified_farmer(self):
        return self.role == ROLE_FARMER and self.kyc_status == KYC_APPROVED

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    farmer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(30), nullable=False, default="kg")
    stock = db.Column(db.Integer, nullable=False, default=0)
    freshness = db.Column(db.String(120))
    image_file = db.Column(db.String(255), nullable=True)
    is_available = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    cart_items = db.relationship("CartItem", backref="product", lazy=True, cascade="all, delete-orphan")
    order_items = db.relationship("OrderItem", backref="product", lazy=True)
    wishlist_items = db.relationship("Wishlist", backref="product", lazy=True, cascade="all, delete-orphan")
    reviews = db.relationship("Review", backref="product", lazy=True)

    @property
    def display_id(self):
        return f"PRD-{self.id:04d}"

    @property
    def in_stock(self):
        return bool(self.is_available and self.stock > 0)

    @property
    def avg_rating(self):
        if not self.reviews:
            return 0
        return round(sum(r.rating for r in self.reviews) / len(self.reviews), 1)


class CartItem(db.Model):
    __tablename__ = "cart_items"

    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=utcnow)

    __table_args__ = (db.UniqueConstraint("buyer_id", "product_id", name="uq_cart_buyer_product"),)

    @property
    def subtotal(self):
        return round(self.product.price * self.quantity, 2)


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    locality_id = db.Column(db.Integer, db.ForeignKey("localities.id"), nullable=True, index=True)
    order_number = db.Column(db.String(30), unique=True, nullable=False)
    total_amount = db.Column(db.Float, nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default="Confirmed")

    delivery_name = db.Column(db.String(120))
    delivery_phone = db.Column(db.String(20))
    delivery_address = db.Column(db.String(255))
    delivery_city = db.Column(db.String(100))
    delivery_pincode = db.Column(db.String(20))
    delivery_slot = db.Column(db.String(60))

    payment_method = db.Column(db.String(20), default="COD")
    payment_status = db.Column(db.String(20), default="Pending")

    coupon_code = db.Column(db.String(30), nullable=True)
    discount_amount = db.Column(db.Float, default=0)
    points_redeemed = db.Column(db.Integer, default=0)
    points_earned = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    locality = db.relationship("Locality", foreign_keys=[locality_id])
    items = db.relationship("OrderItem", backref="order", lazy=True, cascade="all, delete-orphan")
    payments = db.relationship("Payment", backref="order", lazy=True, cascade="all, delete-orphan")
    payouts = db.relationship("FarmerPayout", backref="order", lazy=True)

    @property
    def display_id(self):
        return self.order_number


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    farmer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    product_name = db.Column(db.String(150), nullable=False)
    price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    subtotal = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="Confirmed")

    farmer_ref = db.relationship("User", foreign_keys=[farmer_id])


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    method = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="Pending")
    transaction_ref = db.Column(db.String(60), unique=True)
    created_at = db.Column(db.DateTime, default=utcnow)


class FarmerPayout(db.Model):
    __tablename__ = "farmer_payouts"

    id = db.Column(db.Integer, primary_key=True)
    farmer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=True)
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="Pending")
    created_at = db.Column(db.DateTime, default=utcnow)
    paid_at = db.Column(db.DateTime, nullable=True)


class Wishlist(db.Model):
    __tablename__ = "wishlists"

    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    __table_args__ = (db.UniqueConstraint("buyer_id", "product_id", name="uq_wishlist_buyer_product"),)


class Review(db.Model):
    __tablename__ = "reviews"

    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=True)
    rating = db.Column(db.Integer, nullable=False, default=5)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow)

    __table_args__ = (db.UniqueConstraint("order_id", "product_id", name="uq_review_order_product"),)


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    message = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(30), default="info")
    link = db.Column(db.String(255), nullable=True)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    user = db.relationship("User", backref="notifications", foreign_keys=[user_id])


class Coupon(db.Model):
    __tablename__ = "coupons"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False, index=True)
    discount_type = db.Column(db.String(10), default="percent")  # percent | flat
    discount_value = db.Column(db.Float, nullable=False)
    min_order_amount = db.Column(db.Float, default=0)
    max_uses = db.Column(db.Integer, nullable=True)
    used_count = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    valid_until = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    def is_valid_for(self, order_total):
        if not self.is_active:
            return False, "This coupon is no longer active."
        if self.valid_until and utcnow() > self.valid_until:
            return False, "This coupon has expired."
        if self.max_uses is not None and self.used_count >= self.max_uses:
            return False, "This coupon has reached its usage limit."
        if order_total < (self.min_order_amount or 0):
            return False, f"This coupon needs a minimum order of Rs. {self.min_order_amount:.2f}."
        return True, None

    def compute_discount(self, order_total):
        if self.discount_type == "percent":
            return round(order_total * (min(self.discount_value, 100) / 100), 2)
        return round(min(self.discount_value, order_total), 2)


class PointsTransaction(db.Model):
    __tablename__ = "points_transactions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=True)
    points = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    user = db.relationship("User", backref="points_transactions", foreign_keys=[user_id])


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(80), nullable=False)
    target_type = db.Column(db.String(40), nullable=True)
    target_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    actor = db.relationship("User", foreign_keys=[actor_id])
