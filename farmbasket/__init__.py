import logging
import os
import secrets
from logging.handlers import RotatingFileHandler

from flask import Flask, redirect, url_for, render_template
from flask_login import current_user

from config import Config, DEFAULT_SECRET
from farmbasket.extensions import db, login_manager, csrf, limiter, socketio

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self' ws: wss:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


def _configure_logging(app):
    os.makedirs(app.config["LOG_DIR"], exist_ok=True)
    handler = RotatingFileHandler(
        os.path.join(app.config["LOG_DIR"], "farmbasket.log"), maxBytes=1_000_000, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    handler.setLevel(logging.INFO)
    for logger in (app.logger, logging.getLogger("farmbasket")):
        if handler not in logger.handlers:
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)


def _ensure_secret_key(app, instance_dir):
    """Use FARMBASKET_SECRET_KEY if set, else create and reuse a random key
    stored in instance/secret_key so every install has its own."""
    if app.config["SECRET_KEY"] != DEFAULT_SECRET or app.config.get("TESTING"):
        return
    path = os.path.join(instance_dir, "secret_key")
    if os.path.exists(path):
        key = open(path).read().strip()
    else:
        key = secrets.token_hex(32)
        with open(path, "w") as f:
            f.write(key)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    app.config["SECRET_KEY"] = key


def _check_schema():
    """create_all() never alters existing tables. If the database file comes from
    an older version, stop with a clear message instead of failing later."""
    from sqlalchemy import inspect

    inspector = inspect(db.engine)
    for table in db.metadata.sorted_tables:
        existing = {c["name"] for c in inspector.get_columns(table.name)}
        missing = {c.name for c in table.columns} - existing
        if missing:
            raise RuntimeError(
                f"The database was created by an older version (table '{table.name}' is missing "
                f"{', '.join(sorted(missing))}). Run 'python reset_db.py' to start fresh. "
                "This deletes all existing data."
            )


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    instance_dir = os.path.abspath(os.path.join(app.root_path, "..", "instance"))
    os.makedirs(instance_dir, exist_ok=True)
    for folder in (app.config["UPLOAD_FOLDER"], app.config["PRODUCT_IMAGE_FOLDER"], app.config["KYC_DOC_FOLDER"]):
        os.makedirs(folder, exist_ok=True)

    _ensure_secret_key(app, instance_dir)
    _configure_logging(app)

    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    socketio.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Log in to continue."
    login_manager.login_message_category = "error"

    from farmbasket.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from farmbasket.routes.account import account_bp
    from farmbasket.routes.admin import admin_bp
    from farmbasket.routes.api import api_bp
    from farmbasket.routes.auth import auth_bp
    from farmbasket.routes.buyer import buyer_bp
    from farmbasket.routes.farmer import farmer_bp
    from farmbasket.routes.legal import legal_bp
    from farmbasket.routes.marketplace import marketplace_bp
    from farmbasket.routes.notifications import notifications_bp

    for bp in (auth_bp, marketplace_bp, buyer_bp, farmer_bp, admin_bp, notifications_bp, api_bp,
               account_bp, legal_bp):
        app.register_blueprint(bp)

    csrf.exempt(api_bp)  # authenticated by API key header, not cookies

    @app.template_filter("inr")
    def inr(value):
        return "\u20b9{:,.2f}".format(value or 0)

    @app.template_filter("dt")
    def fmt_datetime(value):
        return value.strftime("%d %b %Y, %I:%M %p") if value else "Not set"

    @app.template_filter("d")
    def fmt_date(value):
        return value.strftime("%d %b %Y") if value else "Not set"

    import farmbasket.socketio_events  # noqa: F401

    @app.context_processor
    def inject_globals():
        data = {
            "business_name": app.config["BUSINESS_NAME"],
            "support_email": app.config["SUPPORT_EMAIL"],
            "unread_notifications": 0,
            "cart_count": 0,
        }
        if current_user.is_authenticated:
            from farmbasket.services.cart_service import CartService
            from farmbasket.services.notification_service import NotificationService
            data["unread_notifications"] = NotificationService.unread_count(current_user.id)
            if current_user.role == "buyer":
                data["cart_count"] = CartService.cart_count(current_user.id)
        return data

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = CSP
        if response.mimetype in ("text/html", "application/json"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.route("/")
    def home():
        if current_user.is_authenticated:
            from farmbasket.routes.auth import dashboard_endpoint
            return redirect(url_for(dashboard_endpoint(current_user.role)))
        return redirect(url_for("marketplace.index"))

    @app.route("/health")
    def health():
        return {"status": "ok"}

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(429)
    def rate_limited(e):
        return render_template("errors/429.html"), 429

    @app.errorhandler(500)
    def server_error(e):
        db.session.rollback()
        return render_template("errors/500.html"), 500

    with app.app_context():
        db.create_all()
        _check_schema()
        if app.config.get("SEED_DEFAULT_LOCALITIES"):
            from farmbasket.repositories.locality_repository import LocalityRepository
            LocalityRepository.seed_defaults_if_empty()

    if not app.config.get("TESTING"):
        from farmbasket.scheduler import init_scheduler
        init_scheduler(app)
        if not app.config["SUPPORT_EMAIL"]:
            app.logger.warning("FARMBASKET_SUPPORT_EMAIL is not set. Legal pages will show no contact address.")

    return app
