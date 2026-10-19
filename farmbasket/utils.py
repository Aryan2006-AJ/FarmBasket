import os
import uuid
from functools import wraps
from urllib.parse import urlparse

from flask import abort, flash, redirect, url_for, current_app, request, jsonify
from flask_login import current_user
from werkzeug.utils import secure_filename


def role_required(*roles):
    """Restrict a route to one or more roles."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            if current_user.role not in roles:
                return abort(403)
            return view_func(*args, **kwargs)

        return wrapped

    return decorator


def safe_redirect_target(default_endpoint, **values):
    """Redirect back to the referring page only if it is on this site."""
    ref = request.referrer
    if ref:
        parsed = urlparse(ref)
        if parsed.netloc == request.host:
            return ref
    return url_for(default_endpoint, **values)


def generate_order_number():
    return "FB" + uuid.uuid4().hex[:10].upper()


def generate_transaction_ref():
    return "TXN" + uuid.uuid4().hex[:12].upper()


def save_uploaded_image(file_storage, folder, max_size=(1000, 1000)):
    """Validate that the upload really is an image, downsize it, and save it
    under a random name. Returns the filename or None."""
    if not file_storage or not file_storage.filename:
        return None

    from PIL import Image, UnidentifiedImageError

    ext = secure_filename(file_storage.filename).rsplit(".", 1)[-1].lower()
    allowed = current_app.config.get("ALLOWED_IMAGE_EXTENSIONS", {"png", "jpg", "jpeg", "webp"})
    if ext not in allowed:
        return None

    os.makedirs(folder, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{ext}"
    full_path = os.path.join(folder, filename)

    try:
        image = Image.open(file_storage.stream)
        image.load()
    except (UnidentifiedImageError, OSError):
        return None

    image.thumbnail(max_size)
    if ext in ("jpg", "jpeg") and image.mode != "RGB":
        image = image.convert("RGB")
    image.save(full_path)
    return filename


def save_uploaded_document(file_storage, folder):
    """Save a KYC document (image or PDF) under a random name."""
    if not file_storage or not file_storage.filename:
        return None
    ext = secure_filename(file_storage.filename).rsplit(".", 1)[-1].lower()
    if ext not in {"png", "jpg", "jpeg", "webp", "pdf"}:
        return None
    os.makedirs(folder, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{ext}"
    file_storage.save(os.path.join(folder, filename))
    return filename


def api_key_required(view_func):
    """Token auth for the JSON API. Clients send their key in X-API-Key."""

    @wraps(view_func)
    def wrapped(*args, **kwargs):
        from farmbasket.models import User

        key = request.headers.get("X-API-Key")
        if not key:
            return jsonify({"error": "Missing X-API-Key header."}), 401
        user = User.query.filter_by(api_key=key).first()
        if not user or not user.is_active:
            return jsonify({"error": "Invalid API key."}), 401
        request.api_user = user
        return view_func(*args, **kwargs)

    return wrapped
