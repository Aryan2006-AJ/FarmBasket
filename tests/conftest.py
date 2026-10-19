import os
import shutil
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import Config
from farmbasket import create_app
from farmbasket.extensions import db
from farmbasket.models import Locality, Product
from farmbasket.repositories.user_repository import UserRepository

PW = "farmpass123"
ADMIN_PW = "adminpass123"

CHECKOUT = dict(
    delivery_name="Buyer Bob", delivery_phone="9876543210", delivery_address="12 Main Road",
    delivery_city="Pune", delivery_pincode="411046", delivery_slot="Morning, 7 am to 10 am",
    payment_method="COD",
)


@pytest.fixture
def app():
    tmp = tempfile.mkdtemp()

    class TestConfig(Config):
        TESTING = True
        WTF_CSRF_ENABLED = False
        RATELIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tmp, "test.db")
        UPLOAD_FOLDER = os.path.join(tmp, "uploads")
        PRODUCT_IMAGE_FOLDER = os.path.join(tmp, "uploads", "products")
        KYC_DOC_FOLDER = os.path.join(tmp, "uploads", "kyc")
        LOG_DIR = os.path.join(tmp, "logs")
        SUPPORT_EMAIL = "help@example.org"

    application = create_app(TestConfig)
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def client(app):
    return app.test_client()


def locality_id(app, name):
    with app.app_context():
        return Locality.query.filter_by(name=name).first().id


def make_user(app, role, email, area="Katraj", name=None, password=PW):
    with app.app_context():
        user = UserRepository.create_user(
            full_name=name or f"{role.title()} {email.split('@')[0]}", email=email, password=password,
            role=role, phone="9876543210", locality_id=locality_id(app, area) if area else None,
            terms_accepted=True)
        return user.id


def login(client, email, password=PW):
    return client.post("/auth/login", data=dict(email=email, password=password), follow_redirects=True)


def logout(client):
    return client.post("/auth/logout", follow_redirects=True)


def add_product(client, farmer_email, name="Tomatoes", stock=10, price=40, category="Vegetables", available=True):
    login(client, farmer_email)
    data = dict(name=name, category=category, description="Fresh", price=str(price), unit="kg",
                stock=str(stock), freshness="Harvested today")
    if available:
        data["is_available"] = "y"
    client.post("/farmer/products/add", data=data, follow_redirects=True)
    logout(client)


def product_id(app, name):
    with app.app_context():
        return Product.query.filter_by(name=name).first().id


@pytest.fixture
def farmer(app):
    make_user(app, "farmer", "farmer@test.com", "Katraj", "Farmer Joe")
    return "farmer@test.com"


@pytest.fixture
def buyer(app):
    make_user(app, "buyer", "buyer@test.com", "Katraj", "Buyer Bob")
    return "buyer@test.com"


@pytest.fixture
def admin(app):
    make_user(app, "admin", "admin@test.com", area=None, name="Admin Asha", password=ADMIN_PW)
    return "admin@test.com"
