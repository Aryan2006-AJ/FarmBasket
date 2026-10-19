"""Guards for the launch rules: no emoji, no dashes, no effects, no third-party
requests, no inline code, no fake claims, working CSRF on every form, and legal pages."""
import os
import re
import shutil
import tempfile

import pytest

from config import Config
from farmbasket import create_app
from tests.conftest import (
    CHECKOUT, PW, ADMIN_PW, add_product, locality_id, login, logout, make_user, product_id,
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SKIP_DIRS = {"venv", "__pycache__", ".git", ".pytest_cache", "vendor", "instance", "uploads", "logs", "node_modules"}
TEXT_EXT = {".py", ".html", ".css", ".js", ".md", ".txt", ".yml", ".yaml", ".ini", ".example", ".cfg", ".toml"}

DASHES = re.compile("[\u2012\u2013\u2014\u2015\u2212]")
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u2300-\u23FF\uFE0F\u200D\u2190-\u21FF]")


def _files(exts=TEXT_EXT, under=None):
    base = os.path.join(ROOT, under) if under else ROOT
    for dp, dn, fn in os.walk(base):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in fn:
            if os.path.splitext(f)[1] in exts or f in ("Dockerfile", ".dockerignore", ".env.example"):
                yield os.path.join(dp, f)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def test_no_emoji_or_dashes_anywhere():
    problems = []
    for path in _files():
        text = _read(path)
        for rx, label in ((DASHES, "dash"), (EMOJI, "emoji/symbol")):
            hit = rx.search(text)
            if hit:
                problems.append(f"{os.path.relpath(path, ROOT)}: {label} U+{ord(hit.group()):04X}")
    assert not problems, problems


def test_banned_effects_stay_out():
    """Allowed: short one-time entrances, hover lift, press feedback. Not allowed: gradients,
    endless loops, scroll-driven or cursor-driven effects."""
    banned = ["gradient", "infinite", "scroll-behavior", "animation-timeline", "backdrop-filter", "cursor: url",
              "mousemove", "mouseover", "IntersectionObserver", 'addEventListener("scroll"',
              "addEventListener('scroll'", "parallax", "requestAnimationFrame", "@keyframes spin", "marquee"]
    problems = []
    for path in list(_files({".css", ".js"}, "farmbasket/static")) + list(_files({".html"}, "farmbasket/templates")):
        low = _read(path).lower()
        for word in banned:
            if word.lower() in low:
                problems.append(f"{os.path.relpath(path, ROOT)}: {word}")
    assert not problems, problems


def _css():
    return _read(os.path.join(ROOT, "farmbasket/static/css/app.css"))


def test_motion_is_short_and_respects_reduced_motion():
    css = _css()
    assert "@media (prefers-reduced-motion: reduce)" in css
    reduced = css.split("@media (prefers-reduced-motion: reduce)")[1]
    assert "animation: none" in reduced and "transition: none" in reduced
    for decl in re.findall(r"(?:animation|transition)(?:-delay|-duration)?\s*:\s*([^;]+);", css):
        for value, unit in re.findall(r"(\d*\.?\d+)(ms|s)\b", decl):
            seconds = float(value) / (1000 if unit == "ms" else 1)
            assert seconds <= 0.5, f"motion longer than 0.5s: {decl}"
    # an animation that ends in 'both' or 'forwards' would block hover and press styles
    assert not re.search(r"animation:[^;]*\b(both|forwards)\b", css)


def _hex(css, name):
    m = re.search(rf"--{name}\s*:\s*(#[0-9a-fA-F]{{6}})", css)
    assert m, name
    return m.group(1)


def _luminance(hexcolor):
    r, g, b = [int(hexcolor[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a, b):
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_colour_pairs_meet_accessible_contrast():
    css = _css()
    names = ("green-900", "green-700", "green-100", "green-50", "orange", "orange-100", "red", "red-100",
             "amber-100", "amber-900", "blue", "blue-100", "grain", "grain-100", "plum", "plum-100",
             "ink", "muted", "cream", "paper")
    c = {n: _hex(css, n) for n in names}
    white, footer, thead, badge_bg = "#ffffff", "#f3f0e5", "#f3f0e5", "#ece8da"
    pairs = [
        ("white on primary buttons", white, c["green-700"]), ("white on orange buttons and counts", white, c["orange"]),
        ("white on toast", white, c["green-900"]), ("danger text on white", c["red"], white),
        ("body text on cream", c["ink"], c["cream"]), ("muted on cream", c["muted"], c["cream"]),
        ("muted on white", c["muted"], white), ("muted on footer", c["muted"], footer),
        ("headings on cream", c["green-900"], c["cream"]), ("headings on table head", c["green-900"], thead),
        ("links on white", c["green-700"], white), ("links on cream", c["green-700"], c["cream"]),
        ("area bar text", c["green-900"], c["green-100"]), ("ok badge", c["green-700"], c["green-100"]),
        ("warning badge", c["amber-900"], c["amber-100"]), ("bad badge", c["red"], c["red-100"]),
        ("neutral badge", "#3b463f", badge_bg),
        ("vegetables", c["green-700"], c["green-100"]), ("fruits", c["orange"], c["orange-100"]),
        ("grains", c["grain"], c["grain-100"]), ("dairy", c["blue"], c["blue-100"]),
        ("spices", c["red"], c["red-100"]), ("other", c["plum"], c["plum-100"]),
        ("success flash", c["ink"], c["green-50"]), ("error flash", c["ink"], c["red-100"]),
        ("notice", c["ink"], c["amber-100"]),
    ]
    low = [(label, round(_contrast(fg, bg), 2)) for label, fg, bg in pairs if _contrast(fg, bg) < 4.5]
    assert not low, low


def test_inline_icons_are_hidden_from_screen_readers():
    for path in _files({".html"}, "farmbasket/templates"):
        for tag in re.findall(r"<svg\b[^>]*>", _read(path)):
            assert "aria-hidden" in tag, f"{os.path.relpath(path, ROOT)}: svg without aria-hidden"


def test_font_is_bundled_locally():
    css = _css()
    assert "../vendor/fonts/plus-jakarta-sans.woff2" in css
    assert os.path.exists(os.path.join(ROOT, "farmbasket/static/vendor/fonts/plus-jakarta-sans.woff2"))
    assert os.path.exists(os.path.join(ROOT, "farmbasket/static/vendor/fonts/plus-jakarta-sans.LICENSE"))


def test_buttons_do_not_change_fill_on_hover():
    css = _read(os.path.join(ROOT, "farmbasket/static/css/app.css"))
    for selector, body in re.findall(r"([^{}]+:hover[^{}]*)\{([^}]*)\}", css):
        assert "background" not in body, f"hover changes background: {selector.strip()}"


def test_no_third_party_requests_and_no_inline_code():
    problems = []
    for path in _files({".html", ".css"}, "farmbasket"):
        text = _read(path)
        if re.search(r"https?://", text):
            problems.append(f"{os.path.relpath(path, ROOT)}: external URL")
        if path.endswith(".html"):
            if re.search(r"\sstyle\s*=", text) or "<style" in text:
                problems.append(f"{os.path.relpath(path, ROOT)}: inline style")
            if re.search(r"\son[a-z]+\s*=", text):
                problems.append(f"{os.path.relpath(path, ROOT)}: inline event handler")
            for m in re.finditer(r"<script\b([^>]*)>", text):
                if "src=" not in m.group(1):
                    problems.append(f"{os.path.relpath(path, ROOT)}: inline script")
    assert not problems, problems


def test_no_fake_content_or_ai_labels():
    banned = ["lorem", "testimonial", "happy customers", "customers served", "trusted by", "made with", "built with",
              "powered by ai", "ai-powered", "generated by", "chatgpt", "claude", "academic demo", "john doe",
              "5000+", "10,000+", "bestseller"]
    problems = []
    for path in list(_files({".html", ".js", ".css"}, "farmbasket")) + [os.path.join(ROOT, "README.md")]:
        low = _read(path).lower()
        for word in banned:
            if word in low:
                problems.append(f"{os.path.relpath(path, ROOT)}: {word}")
    assert not problems, problems


def test_every_post_form_has_a_csrf_token():
    missing = []
    for path in _files({".html"}, "farmbasket/templates"):
        text = _read(path)
        for m in re.finditer(r"<form\b([^>]*)>(.*?)</form>", text, re.S | re.I):
            attrs, body = m.group(1), m.group(2)
            if re.search(r'method\s*=\s*"?post', attrs, re.I) or "method" not in attrs.lower():
                if "csrf" not in body and "hidden_tag" not in body:
                    missing.append(os.path.relpath(path, ROOT))
    assert not missing, missing


@pytest.fixture
def csrf_app():
    tmp = tempfile.mkdtemp()

    class CsrfConfig(Config):
        TESTING = True
        RATELIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tmp, "t.db")
        UPLOAD_FOLDER = os.path.join(tmp, "u")
        PRODUCT_IMAGE_FOLDER = os.path.join(tmp, "u", "p")
        KYC_DOC_FOLDER = os.path.join(tmp, "u", "k")
        LOG_DIR = os.path.join(tmp, "l")
        SECRET_KEY = "test-secret"

    application = create_app(CsrfConfig)
    yield application
    shutil.rmtree(tmp, ignore_errors=True)


def _token(html):
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', html) or re.search(
        rb'value="([^"]+)"[^>]*name="csrf_token"', html)
    assert m, "no csrf token found on page"
    return m.group(1).decode()


def test_buttons_work_with_csrf_protection_on(csrf_app):
    """The 'Bad Request: CSRF token is missing' bug: every button must post a token."""
    make_user(csrf_app, "farmer", "f@test.com", "Katraj")
    make_user(csrf_app, "buyer", "b@test.com", "Katraj")

    c = csrf_app.test_client()
    tok = _token(c.get("/auth/login").data)
    c.post("/auth/login", data=dict(csrf_token=tok, email="f@test.com", password=PW))
    tok = _token(c.get("/farmer/products/add").data)
    r = c.post("/farmer/products/add", data=dict(csrf_token=tok, name="Tomatoes", category="Vegetables", price="40",
                                                 unit="kg", stock="10", is_available="y"), follow_redirects=True)
    assert b"Tomatoes is listed" in r.data
    tok = _token(c.get("/farmer/dashboard").data)
    c.post("/auth/logout", data=dict(csrf_token=tok))

    tok = _token(c.get("/auth/login").data)
    c.post("/auth/login", data=dict(csrf_token=tok, email="b@test.com", password=PW))
    page = c.get("/marketplace/").data
    r = c.post("/marketplace/add-to-cart/1", data=dict(csrf_token=_token(page), quantity="1"), follow_redirects=True)
    assert b"Bad Request" not in r.data and b"is in your cart" in r.data
    page = c.get("/buyer/cart").data
    for action in ("increase/1", "decrease/1"):
        r = c.post(f"/buyer/cart/{action}", data=dict(csrf_token=_token(page)), follow_redirects=True)
        assert r.status_code == 200 and b"Bad Request" not in r.data
    assert c.post("/buyer/cart/remove/1", data={}).status_code == 400  # a post without a token is refused


def test_security_headers(client):
    r = client.get("/marketplace/")
    csp = r.headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp and "unsafe-inline" not in csp
    assert r.headers["X-Frame-Options"] == "DENY" and r.headers["X-Content-Type-Options"] == "nosniff"


def test_legal_pages_are_public_and_linked_everywhere(client, app, buyer):
    for url in ("/privacy", "/terms"):
        r = client.get(url)
        assert r.status_code == 200
        assert b"help@example.org" in r.data and b"Last updated" in r.data
    for url in ("/marketplace/", "/auth/login", "/auth/register"):
        html = client.get(url).data
        assert b'href="/privacy"' in html and b'href="/terms"' in html
    login(client, buyer)
    html = client.get("/buyer/dashboard").data
    assert b'href="/privacy"' in html and b'href="/terms"' in html


def test_legal_pages_show_no_placeholder_when_unconfigured(app):
    app.config["SUPPORT_EMAIL"] = None
    c = app.test_client()
    html = c.get("/privacy").data.decode()
    assert "mailto:" not in html and "example.com" not in html and "your@" not in html
    assert "Governing law" not in c.get("/terms").data.decode()
    app.config["LEGAL_JURISDICTION"] = "Pune, Maharashtra"
    assert "Courts at Pune, Maharashtra" in c.get("/terms").data.decode()


def test_policy_statements_match_the_product(client, app):
    """The policy says we collect no card data and offer cash on delivery only."""
    html = client.get("/privacy").data.decode().lower()
    assert "card numbers" in html and "cash on delivery" in html
    from farmbasket.forms import CheckoutForm
    with app.test_request_context():
        assert [c[0] for c in CheckoutForm().payment_method.choices] == ["COD"]


def test_every_page_renders_for_every_role(client, app, farmer, buyer, admin):
    add_product(client, farmer, stock=10)
    login(client, buyer)
    client.post(f"/marketplace/add-to-cart/{product_id(app, 'Tomatoes')}")
    client.post("/buyer/checkout", data=CHECKOUT)
    logout(client)

    def visit(email, password):
        c = app.test_client()
        if email:
            login(c, email, password)
        for rule in app.url_map.iter_rules():
            if "GET" not in rule.methods or rule.arguments or rule.endpoint == "static":
                continue
            r = c.get(rule.rule)
            assert r.status_code < 500, (email, rule.rule, r.status_code)
        return c

    visit(None, None)
    visit(buyer, PW)
    visit(farmer, PW)
    visit(admin, ADMIN_PW)

    c = app.test_client()
    login(c, buyer)
    for url in ("/buyer/orders/1", "/buyer/order/confirmation/1", "/marketplace/product/1", "/marketplace/set-area"):
        assert c.get(url).status_code == 200, url
    logout(c)
    login(c, admin, ADMIN_PW)
    assert c.get(f"/admin/localities/{locality_id(app, 'Katraj')}").status_code == 200


def test_login_is_rate_limited_but_browsing_is_not():
    tmp = tempfile.mkdtemp()

    class LimitedConfig(Config):
        TESTING = True
        WTF_CSRF_ENABLED = False
        RATELIMIT_ENABLED = True
        RATELIMIT_STORAGE_URI = "memory://"
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tmp, "t.db")
        UPLOAD_FOLDER = os.path.join(tmp, "u")
        PRODUCT_IMAGE_FOLDER = os.path.join(tmp, "u", "p")
        KYC_DOC_FOLDER = os.path.join(tmp, "u", "k")
        LOG_DIR = os.path.join(tmp, "l")

    application = create_app(LimitedConfig)
    try:
        c = application.test_client()
        assert all(c.get("/marketplace/").status_code == 200 for _ in range(60))
        codes = [c.post("/auth/login", data=dict(email="a@test.com", password="x" * 9)).status_code
                 for _ in range(20)]
        assert 429 in codes
        assert b"Too many attempts" in c.post("/auth/login", data=dict(email="a@test.com", password="x" * 9)).data
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
