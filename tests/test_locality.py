"""Hyperlocal behaviour: a buyer sees and orders from farmers in their own area."""
from tests.conftest import add_product, locality_id, login, logout, make_user, product_id


def _two_areas(client, app):
    make_user(app, "farmer", "katraj_farmer@test.com", "Katraj", "Katraj Farmer")
    make_user(app, "farmer", "kothrud_farmer@test.com", "Kothrud", "Kothrud Farmer")
    add_product(client, "katraj_farmer@test.com", "Katraj Tomatoes")
    add_product(client, "kothrud_farmer@test.com", "Kothrud Spinach")


def test_buyer_sees_only_own_area_by_default(client, app):
    _two_areas(client, app)
    make_user(app, "buyer", "b@test.com", "Katraj")
    login(client, "b@test.com")
    r = client.get("/marketplace/")
    assert b"Katraj Tomatoes" in r.data and b"Kothrud Spinach" not in r.data


def test_show_all_lists_other_areas_but_blocks_ordering(client, app):
    _two_areas(client, app)
    make_user(app, "buyer", "b@test.com", "Katraj")
    login(client, "b@test.com")
    r = client.get("/marketplace/?all=1")
    assert b"Katraj Tomatoes" in r.data and b"Kothrud Spinach" in r.data
    assert b"Not delivered to your area" in r.data


def test_changing_area_is_saved_to_the_profile(client, app):
    _two_areas(client, app)
    make_user(app, "buyer", "b@test.com", "Katraj")
    login(client, "b@test.com")
    client.post("/marketplace/set-area", data=dict(locality_id=str(locality_id(app, "Kothrud"))))
    r = client.get("/marketplace/")
    assert b"Kothrud Spinach" in r.data and b"Katraj Tomatoes" not in r.data
    logout(client)
    login(client, "b@test.com")
    assert b"Kothrud Spinach" in client.get("/marketplace/").data


def test_guest_picks_an_area_for_the_session(client, app):
    _two_areas(client, app)
    r = client.get("/marketplace/")
    assert b"Choose your area" in r.data
    client.post("/marketplace/set-area", data=dict(locality_id=str(locality_id(app, "Katraj"))))
    r = client.get("/marketplace/")
    assert b"Katraj Tomatoes" in r.data and b"Kothrud Spinach" not in r.data


def test_empty_area_explains_why(client, app):
    _two_areas(client, app)
    make_user(app, "buyer", "b@test.com", "Baner")
    login(client, "b@test.com")
    r = client.get("/marketplace/")
    assert b"No farmers deliver to Baner" in r.data and b"Show all areas" in r.data


def test_unavailable_products_are_listed_separately(client, app):
    make_user(app, "farmer", "f@test.com", "Katraj")
    make_user(app, "buyer", "b@test.com", "Katraj")
    add_product(client, "f@test.com", "Fresh Okra", stock=5)
    add_product(client, "f@test.com", "Sold Out Peas", stock=0)
    add_product(client, "f@test.com", "Hidden Beans", stock=5, available=False)
    login(client, "b@test.com")
    r = client.get("/marketplace/")
    html = r.data.decode()
    assert "Currently unavailable in Katraj, Pune" in html
    assert "Fresh Okra" in html and "Sold Out Peas" in html and "Hidden Beans" in html
    assert "Out of stock" in html and "Unlisted" in html
    available_part = html.split("Currently unavailable")[0]
    assert "Fresh Okra" in available_part and "Sold Out Peas" not in available_part


def test_search_suggestions_respect_area(client, app):
    _two_areas(client, app)
    make_user(app, "buyer", "b@test.com", "Katraj")
    login(client, "b@test.com")
    names = [i["name"] for i in client.get("/marketplace/api/search-suggestions?q=sp").get_json()]
    assert names == []
    names = [i["name"] for i in client.get("/marketplace/api/search-suggestions?q=tom").get_json()]
    assert names == ["Katraj Tomatoes"]


def test_admin_adds_and_closes_areas(client, app, admin):
    login(client, admin, "adminpass123")
    r = client.post("/admin/localities", data=dict(name="Magarpatta", city="Pune"), follow_redirects=True)
    assert b"Magarpatta, Pune added" in r.data
    r = client.post("/admin/localities", data=dict(name="magarpatta", city="pune"), follow_redirects=True)
    assert b"already exists" in r.data


def test_admin_area_detail_shows_what_is_missing(client, app, admin):
    make_user(app, "farmer", "f@test.com", "Katraj")
    add_product(client, "f@test.com", "Fresh Okra", stock=5, category="Vegetables")
    add_product(client, "f@test.com", "Sold Out Milk", stock=0, category="Dairy")
    login(client, admin, "adminpass123")
    r = client.get(f"/admin/localities/{locality_id(app, 'Katraj')}")
    html = r.data.decode()
    assert "Fresh Okra" in html and "Sold Out Milk" in html
    assert "No product in stock for" in html and "Dairy" in html and "Fruits" in html
    assert "Vegetables, " not in html.split("No product in stock for")[1].split("</div>")[0]


def test_admin_dashboard_counts_buyers_and_farmers_per_area(client, app, admin):
    make_user(app, "farmer", "f@test.com", "Katraj")
    make_user(app, "buyer", "b1@test.com", "Katraj")
    make_user(app, "buyer", "b2@test.com", "Katraj")
    login(client, admin, "adminpass123")
    page = client.get("/admin/dashboard").data.decode()
    assert "Buyers" in page and "Farmers" in page
    from farmbasket.routes.admin import _locality_stats
    from farmbasket.models import Locality
    with app.app_context():
        s = _locality_stats(Locality.query.filter_by(name="Katraj").one())
        assert (s["buyers"], s["farmers"]) == (2, 1)
