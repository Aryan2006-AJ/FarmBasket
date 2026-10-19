import io

from tests.conftest import (
    CHECKOUT, PW, add_product, locality_id, login, logout, make_user, product_id,
)


def test_product_appears_in_same_area_shop(client, app, farmer, buyer):
    add_product(client, farmer)
    login(client, buyer)
    r = client.get("/marketplace/")
    assert b"Tomatoes" in r.data and b"Delivering to" in r.data


def test_add_to_cart_caps_at_stock(client, app, farmer, buyer):
    add_product(client, farmer, stock=2)
    login(client, buyer)
    client.post(f"/marketplace/add-to-cart/{product_id(app, 'Tomatoes')}", data=dict(quantity="10"))
    from farmbasket.models import CartItem
    with app.app_context():
        assert CartItem.query.one().quantity == 2


def test_cannot_add_product_from_another_area(client, app, farmer, buyer):
    make_user(app, "farmer", "other@test.com", "Kothrud")
    add_product(client, "other@test.com", name="Kothrud Spinach")
    login(client, buyer)
    r = client.post(f"/marketplace/add-to-cart/{product_id(app, 'Kothrud Spinach')}", follow_redirects=True)
    assert b"does not deliver to your area" in r.data
    from farmbasket.models import CartItem
    with app.app_context():
        assert CartItem.query.count() == 0


def test_cart_quantity_controls_and_isolation(client, app, farmer, buyer):
    add_product(client, farmer, stock=5)
    make_user(app, "buyer", "second@test.com", "Katraj")
    pid = product_id(app, "Tomatoes")
    login(client, buyer)
    client.post(f"/marketplace/add-to-cart/{pid}")
    client.post("/buyer/cart/increase/1")
    assert b"Tomatoes" in client.get("/buyer/cart").data
    logout(client)
    login(client, "second@test.com")
    assert b"Your cart is empty" in client.get("/buyer/cart").data
    assert client.post("/buyer/cart/remove/1").status_code == 302  # cannot touch someone else's row
    logout(client)
    login(client, buyer)
    assert b"Tomatoes" in client.get("/buyer/cart").data


def _place_order(client, app, buyer, quantity=3, **extra):
    login(client, buyer)
    client.post(f"/marketplace/add-to-cart/{product_id(app, 'Tomatoes')}", data=dict(quantity=str(quantity)))
    r = client.post("/buyer/checkout", data=dict(CHECKOUT, **extra), follow_redirects=True)
    return r


def test_checkout_creates_order_updates_stock_and_clears_cart(client, app, farmer, buyer):
    add_product(client, farmer, stock=10, price=40)
    r = _place_order(client, app, buyer, quantity=3)
    assert b"Order confirmed" in r.data and b"Morning, 7 am to 10 am" in r.data
    from farmbasket.models import Product, Order, CartItem, FarmerPayout
    with app.app_context():
        assert Product.query.first().stock == 7
        order = Order.query.one()
        assert order.total_amount == 120 and order.status == "Confirmed" and order.locality.name == "Katraj"
        assert CartItem.query.count() == 0
        assert FarmerPayout.query.one().status == "Pending"


def test_checkout_requires_valid_delivery_details(client, app, farmer, buyer):
    add_product(client, farmer)
    r = _place_order(client, app, buyer, delivery_pincode="12")
    assert b"6 digit pincode" in r.data
    from farmbasket.models import Order
    with app.app_context():
        assert Order.query.count() == 0


def test_cannot_check_out_after_changing_area(client, app, farmer, buyer):
    add_product(client, farmer)
    login(client, buyer)
    client.post(f"/marketplace/add-to-cart/{product_id(app, 'Tomatoes')}")
    client.post("/marketplace/set-area", data=dict(locality_id=str(locality_id(app, "Kothrud"))))
    r = client.get("/buyer/checkout", follow_redirects=True)
    assert b"not delivered to your area" in r.data.lower()
    r = client.get("/buyer/cart")
    assert b"Not delivered to your area" in r.data


def test_coupon_discount_and_single_use_limit(client, app, farmer, buyer, admin):
    add_product(client, farmer, stock=10, price=100)
    login(client, admin, "adminpass123")
    client.post("/admin/coupons", data=dict(code="save10", discount_type="percent", discount_value="10",
                                            min_order_amount="0", max_uses="1"))
    logout(client)
    _place_order(client, app, buyer, quantity=2, coupon_code="SAVE10")
    from farmbasket.models import Order, Coupon
    with app.app_context():
        assert Order.query.one().total_amount == 180
        assert Coupon.query.one().used_count == 1
    client.post(f"/marketplace/add-to-cart/{product_id(app, 'Tomatoes')}")
    r = client.post("/buyer/checkout", data=dict(CHECKOUT, coupon_code="SAVE10"), follow_redirects=True)
    assert b"usage limit" in r.data


def test_cannot_oversell_stock(client, app, farmer, buyer):
    add_product(client, farmer, stock=3)
    make_user(app, "buyer", "late@test.com", "Katraj")
    login(client, buyer)
    client.post(f"/marketplace/add-to-cart/{product_id(app, 'Tomatoes')}", data=dict(quantity="3"))
    # another buyer takes the stock first
    other = app.test_client()
    login(other, "late@test.com")
    other.post(f"/marketplace/add-to-cart/{product_id(app, 'Tomatoes')}", data=dict(quantity="3"))
    assert b"Order confirmed" in other.post("/buyer/checkout", data=CHECKOUT, follow_redirects=True).data
    r = client.post("/buyer/checkout", data=CHECKOUT, follow_redirects=True)
    assert b"Not enough stock" in r.data
    from farmbasket.models import Product
    with app.app_context():
        assert Product.query.first().stock == 0


def test_cancel_restocks_and_reverses_points(client, app, farmer, buyer):
    add_product(client, farmer, stock=10, price=100)
    _place_order(client, app, buyer, quantity=5)  # 500 total, 5 points earned
    from farmbasket.models import Product, User, Order, FarmerPayout
    with app.app_context():
        assert User.query.filter_by(email=buyer).one().loyalty_points == 5
    r = client.post("/buyer/orders/1/cancel", follow_redirects=True)
    assert b"was cancelled" in r.data
    with app.app_context():
        assert Product.query.first().stock == 10
        assert Order.query.one().status == "Cancelled"
        assert FarmerPayout.query.one().status == "Cancelled"
        assert User.query.filter_by(email=buyer).one().loyalty_points == 0


def test_farmer_moves_order_forward_one_step_and_cannot_cancel(client, app, farmer, buyer):
    add_product(client, farmer)
    _place_order(client, app, buyer, quantity=1)
    logout(client)
    login(client, farmer)
    page = client.get("/farmer/orders").data
    assert b"Buyer Bob" in page and b"12 Main Road" in page and b"Morning, 7 am to 10 am" in page
    for expected in ("Packed", "Out for Delivery", "Delivered"):
        client.post("/farmer/orders/1/advance")
        from farmbasket.models import OrderItem
        with app.app_context():
            assert OrderItem.query.one().status == expected
    r = client.post("/farmer/orders/1/advance", follow_redirects=True)
    assert b"already delivered" in r.data
    r = client.post("/farmer/orders/1/status", data=dict(status="Cancelled"))
    assert r.status_code == 404


def test_delivery_completes_cod_payment_and_payout(client, app, farmer, buyer, admin):
    add_product(client, farmer)
    _place_order(client, app, buyer, quantity=1)
    logout(client)
    login(client, farmer)
    for _ in range(3):
        client.post("/farmer/orders/1/advance")
    logout(client)
    login(client, admin, "adminpass123")
    client.post("/admin/payouts/run-batch")
    from farmbasket.models import Order, FarmerPayout, Payment
    with app.app_context():
        assert Order.query.one().status == "Delivered" and Order.query.one().payment_status == "Paid"
        assert Payment.query.one().status == "Paid"
        assert FarmerPayout.query.one().status == "Paid"


def test_cannot_cancel_once_out_for_delivery(client, app, farmer, buyer):
    add_product(client, farmer)
    _place_order(client, app, buyer, quantity=1)
    logout(client)
    login(client, farmer)
    client.post("/farmer/orders/1/advance")
    client.post("/farmer/orders/1/advance")
    logout(client)
    login(client, buyer)
    r = client.post("/buyer/orders/1/cancel", follow_redirects=True)
    assert b"out for delivery" in r.data


def test_farmer_cannot_touch_another_farmers_items(client, app, farmer, buyer):
    make_user(app, "farmer", "rival@test.com", "Katraj")
    add_product(client, farmer)
    _place_order(client, app, buyer, quantity=1)
    logout(client)
    login(client, "rival@test.com")
    assert client.post("/farmer/orders/1/advance").status_code == 404
    assert b"Tomatoes" not in client.get("/farmer/orders").data


def test_review_only_after_delivery_and_only_once(client, app, farmer, buyer):
    add_product(client, farmer)
    _place_order(client, app, buyer, quantity=1)
    pid = product_id(app, "Tomatoes")
    r = client.post(f"/buyer/orders/1/review/{pid}", data=dict(rating="5", comment="Good"), follow_redirects=True)
    assert b"after it has been delivered" in r.data
    logout(client)
    login(client, farmer)
    for _ in range(3):
        client.post("/farmer/orders/1/advance")
    logout(client)
    login(client, buyer)
    r = client.post(f"/buyer/orders/1/review/{pid}", data=dict(rating="4", comment="Fresh"), follow_redirects=True)
    assert b"review is saved" in r.data
    r = client.post(f"/buyer/orders/1/review/{pid}", data=dict(rating="1", comment="Again"), follow_redirects=True)
    assert b"already reviewed" in r.data
    assert b"Fresh" in client.get(f"/marketplace/product/{pid}").data


def test_buyer_cannot_view_another_buyers_order(client, app, farmer, buyer):
    add_product(client, farmer)
    _place_order(client, app, buyer, quantity=1)
    logout(client)
    make_user(app, "buyer", "snoop@test.com", "Katraj")
    login(client, "snoop@test.com")
    assert client.get("/buyer/orders/1").status_code == 404
    assert client.get("/buyer/orders/1/invoice").status_code == 404


def test_invoice_pdf(client, app, farmer, buyer):
    add_product(client, farmer)
    _place_order(client, app, buyer, quantity=1)
    r = client.get("/buyer/orders/1/invoice")
    assert r.status_code == 200 and r.mimetype == "application/pdf" and r.data.startswith(b"%PDF")


def test_deleting_ordered_product_unlists_it_instead_of_crashing(client, app, farmer, buyer):
    add_product(client, farmer)
    _place_order(client, app, buyer, quantity=1)
    logout(client)
    login(client, farmer)
    r = client.post(f"/farmer/products/delete/{product_id(app, 'Tomatoes')}", follow_redirects=True)
    assert r.status_code == 200 and b"unlisted instead of deleted" in r.data
    from farmbasket.models import Product
    with app.app_context():
        assert Product.query.one().is_available is False


def test_product_without_orders_is_deleted(client, app, farmer):
    add_product(client, farmer)
    login(client, farmer)
    r = client.post(f"/farmer/products/delete/{product_id(app, 'Tomatoes')}", follow_redirects=True)
    assert b"was deleted" in r.data


def test_photo_upload_accepts_images_and_rejects_fakes(client, app, farmer):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), "gray").save(buf, "PNG")
    buf.seek(0)
    login(client, farmer)
    data = dict(name="Mangoes", category="Fruits", price="100", unit="dozen", stock="5", is_available="y",
                photo=(buf, "mango.png"))
    client.post("/farmer/products/add", data=data, content_type="multipart/form-data")
    from farmbasket.models import Product
    with app.app_context():
        filename = Product.query.one().image_file
        assert filename
    assert client.get(f"/marketplace/uploads/products/{filename}").status_code == 200
    data = dict(name="Fake", category="Fruits", price="10", unit="kg", stock="5", is_available="y",
                photo=(io.BytesIO(b"not an image"), "fake.png"))
    client.post("/farmer/products/add", data=data, content_type="multipart/form-data")
    with app.app_context():
        assert Product.query.filter_by(name="Fake").one().image_file is None
