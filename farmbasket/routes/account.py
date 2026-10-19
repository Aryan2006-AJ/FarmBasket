from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user

from farmbasket.extensions import db
from farmbasket.services.audit_service import AuditService

account_bp = Blueprint("account", __name__, url_prefix="/account")


@account_bp.route("/api-key")
@login_required
def api_key():
    return render_template("account/api_key.html")


@account_bp.route("/api-key/generate", methods=["POST"])
@login_required
def generate_api_key():
    current_user.generate_api_key()
    db.session.commit()
    AuditService.log(current_user.id, "API key generated", "User", current_user.id)
    flash("New API key created. Any previous key no longer works.", "success")
    return redirect(url_for("account.api_key"))
