import os
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

DEFAULT_SECRET = "dev-only-secret-change-before-launch"


def _bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class Config:
    SECRET_KEY = os.environ.get("FARMBASKET_SECRET_KEY", DEFAULT_SECRET)

    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "instance", "database.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    PRODUCT_IMAGE_FOLDER = os.path.join(UPLOAD_FOLDER, "products")
    KYC_DOC_FOLDER = os.path.join(UPLOAD_FOLDER, "kyc")
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB

    WTF_CSRF_ENABLED = True

    # Session cookie hardening. Set FARMBASKET_HTTPS=true when served over HTTPS.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("FARMBASKET_HTTPS", False)

    # Rate limiting is applied only to login, registration, 2FA and the API.
    # There is deliberately no site-wide default limit.
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")

    # Business details shown on the legal pages and in the footer.
    BUSINESS_NAME = os.environ.get("FARMBASKET_BUSINESS_NAME", "FarmBasket")
    SUPPORT_EMAIL = os.environ.get("FARMBASKET_SUPPORT_EMAIL", "").strip() or None
    LEGAL_JURISDICTION = os.environ.get("FARMBASKET_JURISDICTION", "").strip() or None
    LEGAL_LAST_UPDATED = "15 October 2026"

    MIN_PASSWORD_LENGTH = 8

    # Loyalty program
    LOYALTY_POINTS_PER_100_RUPEES = 1
    LOYALTY_POINT_VALUE_RUPEES = 1

    # Delivery windows offered at checkout. Stored as text on the order.
    DELIVERY_SLOTS = [
        "Morning, 7 am to 10 am",
        "Afternoon, 12 pm to 3 pm",
        "Evening, 5 pm to 8 pm",
    ]

    # Serviceable areas created on first run if the table is empty.
    # Admins can add, rename and switch areas off from the admin panel.
    SEED_DEFAULT_LOCALITIES = True

    LOG_DIR = os.path.join(BASE_DIR, "logs")
