import io

import pyotp

from tests.conftest import ADMIN_PW, PW, add_product, login, logout, make_user, product_id


def test_admin_pages_render(client, app, admin, farmer, buyer):
    add_product(client, farmer)
    login(client, admin, ADMIN_PW)
    for url in ("/admin/dashboard", "/admin/users", "/admin/farmers", "/admin/localities", "/admin/products",
                "/admin/orders", "/admin/payments", "/admin/coupons", "/admin/analytics", "/admin/audit-log",
                "/admin/api/analytics/revenue-trend", "/admin/api/analytics/category-breakdown",
                "/admin/api/analytics/order-status"):
        assert client.get(url).status_code == 200, url


def test_csv_export_blocks_formula_injection(client, app, admin):
    make_user(app, "buyer", "evil@test.com", "Katraj", name="=HYPERLINK(\"http://x\")")
    login(client, admin, ADMIN_PW)
    body = client.get("/admin/export/users.csv").data.decode()
    assert "'=HYPERLINK" in body and ",=HYPERLINK" not in body


def test_verification_flow_and_document_access(client, app, admin, farmer, buyer):
    login(client, farmer)
    client.post("/farmer/verification", data=dict(document=(io.BytesIO(b"%PDF-1.4 test"), "id.pdf")),
                content_type="multipart/form-data", follow_redirects=True)
    from farmbasket.models import User
    from farmbasket.extensions import db
    with app.app_context():
        fid = User.query.filter_by(email=farmer).one().id
        assert db.session.get(User, fid).kyc_status == "Pending"
    assert client.get(f"/admin/farmers/{fid}/document").status_code == 403  # farmers cannot open documents
    logout(client)
    login(client, buyer)
    assert client.get(f"/admin/farmers/{fid}/document").status_code == 403
    logout(client)
    login(client, admin, ADMIN_PW)
    assert b"Open submitted document" in client.get("/admin/farmers").data
    assert client.get(f"/admin/farmers/{fid}/document").status_code == 200
    client.post(f"/admin/farmers/{fid}/verify", data=dict(decision="approve"))
    with app.app_context():
        assert db.session.get(User, fid).is_verified_farmer
    assert client.post(f"/admin/farmers/{fid}/verify", data=dict(decision="bogus")).status_code == 400


def test_rejecting_verification_records_reason(client, app, admin, farmer):
    login(client, farmer)
    client.post("/farmer/verification", data=dict(document=(io.BytesIO(b"x"), "id.png")),
                content_type="multipart/form-data")
    logout(client)
    login(client, admin, ADMIN_PW)
    from farmbasket.models import User
    with app.app_context():
        fid = User.query.filter_by(email=farmer).one().id
    client.post(f"/admin/farmers/{fid}/verify", data=dict(decision="reject", notes="Photo is blurry"))
    logout(client)
    login(client, farmer)
    assert b"Photo is blurry" in client.get("/farmer/verification").data


def test_verified_label_shows_in_shop(client, app, admin, farmer, buyer):
    add_product(client, farmer)
    login(client, buyer)
    assert b"Verified" not in client.get("/marketplace/").data
    logout(client)
    from farmbasket.models import User
    from farmbasket.extensions import db
    with app.app_context():
        User.query.filter_by(email=farmer).one().kyc_status = "Approved"
        db.session.commit()
    login(client, buyer)
    assert b"Verified" in client.get("/marketplace/").data


def test_api_key_flow_and_area_scoping(client, app, buyer, farmer):
    make_user(app, "farmer", "other@test.com", "Kothrud")
    add_product(client, farmer, "Katraj Tomatoes")
    add_product(client, "other@test.com", "Kothrud Spinach")
    assert client.get("/api/v1/products").status_code == 401
    assert client.get("/api/v1/products", headers={"X-API-Key": "nope"}).status_code == 401
    login(client, buyer)
    client.post("/account/api-key/generate")
    from farmbasket.models import User
    with app.app_context():
        key = User.query.filter_by(email=buyer).one().api_key
    logout(client)
    r = client.get("/api/v1/products", headers={"X-API-Key": key})
    assert [p["name"] for p in r.get_json()["products"]] == ["Katraj Tomatoes"]
    assert client.get("/api/v1/me", headers={"X-API-Key": key}).get_json()["area"] == "Katraj, Pune"


def test_two_factor_setup_and_login(client, app, admin):
    login(client, admin, ADMIN_PW)
    client.get("/auth/2fa-setup")
    from farmbasket.models import User
    with app.app_context():
        secret = User.query.filter_by(email=admin).one().totp_secret
    client.post("/auth/2fa-setup", data=dict(code=pyotp.TOTP(secret).now()))
    assert b"Two-factor authentication is on" in client.get("/auth/2fa-setup").data
    logout(client)
    r = client.post("/auth/login", data=dict(email=admin, password=ADMIN_PW), follow_redirects=True)
    assert b"Two-factor check" in r.data
    assert b"Dashboard" in client.post("/auth/2fa-verify", data=dict(code=pyotp.TOTP(secret).now()),
                                       follow_redirects=True).data
    client.post("/auth/2fa-disable")
    with app.app_context():
        assert User.query.filter_by(email=admin).one().totp_enabled is False


def test_notifications_page_marks_read(client, app, farmer, buyer):
    add_product(client, farmer)
    login(client, buyer)
    client.post(f"/marketplace/add-to-cart/{product_id(app, 'Tomatoes')}")
    from tests.conftest import CHECKOUT
    client.post("/buyer/checkout", data=CHECKOUT)
    logout(client)
    login(client, farmer)
    assert client.get("/notifications/api/unread-count").get_json()["count"] >= 1
    assert b"New order" in client.get("/notifications/").data
    assert client.get("/notifications/api/unread-count").get_json()["count"] == 0
