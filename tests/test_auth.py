from tests.conftest import PW, locality_id, login, logout, make_user

REGISTER = dict(full_name="New Person", email="new@test.com", phone="9876543210", role="buyer",
                password=PW, confirm_password=PW, accept_terms="y")


def _register(client, app, **overrides):
    data = dict(REGISTER, locality_id=str(locality_id(app, "Katraj")))
    data.update(overrides)
    return client.post("/auth/register", data=data, follow_redirects=True)


def test_register_then_login_reaches_dashboard(client, app):
    r = _register(client, app)
    assert b"Your account is ready" in r.data
    r = login(client, "new@test.com")
    assert b"Hello, New" in r.data


def test_register_requires_accepting_terms(client, app):
    data = dict(REGISTER, locality_id=str(locality_id(app, "Katraj")))
    data.pop("accept_terms")
    r = client.post("/auth/register", data=data, follow_redirects=True)
    assert b"must accept the Terms" in r.data


def test_register_rejects_short_password(client, app):
    r = _register(client, app, password="short1", confirm_password="short1")
    assert b"at least 8" in r.data.lower() or b"between 8" in r.data.lower() or b"8 and" in r.data.lower()


def test_register_requires_a_real_area(client, app):
    r = _register(client, app, locality_id="9999")
    assert b"Your account is ready" not in r.data


def test_duplicate_email_rejected(client, app, buyer):
    r = _register(client, app, email=buyer)
    assert b"already exists" in r.data


def test_closed_area_not_offered_at_registration(client, app, admin):
    login(client, admin, "adminpass123")
    lid = locality_id(app, "Kothrud")
    client.post(f"/admin/localities/{lid}/toggle", follow_redirects=True)
    logout(client)
    r = client.get("/auth/register")
    assert b"Kothrud" not in r.data and b"Katraj" in r.data


def test_wrong_password_uses_generic_message(client, buyer):
    r = client.post("/auth/login", data=dict(email=buyer, password="wrong-password"), follow_redirects=True)
    assert b"Incorrect email or password" in r.data
    r = client.post("/auth/login", data=dict(email="nobody@test.com", password="x" * 9), follow_redirects=True)
    assert b"Incorrect email or password" in r.data


def test_login_required_message(client):
    r = client.get("/buyer/dashboard", follow_redirects=True)
    assert b"Log in to continue" in r.data


def test_roles_are_separated(client, app, buyer, farmer, admin):
    login(client, buyer)
    assert client.get("/admin/dashboard").status_code == 403
    assert client.get("/farmer/dashboard").status_code == 403
    logout(client)
    login(client, farmer)
    assert client.get("/buyer/dashboard").status_code == 403
    assert client.get("/admin/dashboard").status_code == 403


def test_logout_is_post_only(client, buyer):
    login(client, buyer)
    assert client.get("/auth/logout").status_code == 405
    logout(client)
    assert b"Log in to continue" in client.get("/buyer/dashboard", follow_redirects=True).data


def test_deactivated_user_cannot_log_in_or_keep_session(client, app, admin, buyer):
    login(client, buyer)
    other = app.test_client()
    login(other, admin, "adminpass123")
    from farmbasket.repositories.user_repository import UserRepository
    with app.app_context():
        uid = UserRepository.get_by_email(buyer).id
    other.post(f"/admin/users/{uid}/toggle-active", follow_redirects=True)
    assert b"Log in to continue" in client.get("/buyer/dashboard", follow_redirects=True).data
    logout(client)
    r = client.post("/auth/login", data=dict(email=buyer, password=PW), follow_redirects=True)
    assert b"deactivated" in r.data
