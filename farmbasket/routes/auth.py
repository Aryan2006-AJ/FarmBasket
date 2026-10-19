import base64
import io

import qrcode
from flask import Blueprint, render_template, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user

from farmbasket.extensions import db, limiter
from farmbasket.forms import RegisterForm, LoginForm, TwoFactorSetupForm, TwoFactorVerifyForm
from farmbasket.repositories.locality_repository import LocalityRepository
from farmbasket.repositories.user_repository import UserRepository
from farmbasket.services.audit_service import AuditService
from farmbasket.services.auth_service import AuthService
from farmbasket.services.twofactor_service import TwoFactorService

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def dashboard_endpoint(role):
    return {"buyer": "buyer.dashboard", "farmer": "farmer.dashboard", "admin": "admin.dashboard"}.get(
        role, "marketplace.index")


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("20 per hour", methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for(dashboard_endpoint(current_user.role)))

    localities = LocalityRepository.list_active()
    form = RegisterForm()
    form.locality_id.choices = [(l.id, l.label) for l in localities]

    if form.validate_on_submit():
        user, error = AuthService.register(
            full_name=form.full_name.data, email=form.email.data, password=form.password.data,
            role=form.role.data, phone=form.phone.data, locality_id=form.locality_id.data,
            terms_accepted=form.accept_terms.data,
        )
        if error:
            flash(error, "error")
        else:
            flash("Your account is ready. Log in to continue.", "success")
            return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form=form, has_localities=bool(localities))


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("15 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for(dashboard_endpoint(current_user.role)))

    form = LoginForm()
    if form.validate_on_submit():
        user, error = AuthService.authenticate(form.email.data, form.password.data)
        if error:
            flash(error, "error")
        elif user.role == "admin" and user.totp_enabled:
            session["pending_2fa_user_id"] = user.id
            return redirect(url_for("auth.verify_2fa"))
        else:
            login_user(user)
            return redirect(url_for(dashboard_endpoint(user.role)))

    return render_template("auth/login.html", form=form)


@auth_bp.route("/2fa-verify", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def verify_2fa():
    user_id = session.get("pending_2fa_user_id")
    user = UserRepository.get_by_id(user_id) if user_id else None
    if not user:
        session.pop("pending_2fa_user_id", None)
        return redirect(url_for("auth.login"))

    form = TwoFactorVerifyForm()
    if form.validate_on_submit():
        if TwoFactorService.verify(user.totp_secret, form.code.data):
            session.pop("pending_2fa_user_id", None)
            login_user(user)
            return redirect(url_for(dashboard_endpoint(user.role)))
        flash("That code is not correct. Try the current code from your authenticator app.", "error")

    return render_template("auth/verify_2fa.html", form=form)


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/2fa-setup", methods=["GET", "POST"])
@login_required
def setup_2fa():
    if current_user.role != "admin":
        flash("Two-factor authentication is available for admin accounts only.", "error")
        return redirect(url_for(dashboard_endpoint(current_user.role)))

    if current_user.totp_enabled:
        return render_template("auth/manage_2fa.html")

    if not current_user.totp_secret:
        current_user.totp_secret = TwoFactorService.generate_secret()
        db.session.commit()

    uri = TwoFactorService.provisioning_uri(current_user.totp_secret, current_user.email)
    buf = io.BytesIO()
    qrcode.make(uri).save(buf, format="PNG")
    qr_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    form = TwoFactorSetupForm()
    if form.validate_on_submit():
        if TwoFactorService.verify(current_user.totp_secret, form.code.data):
            current_user.totp_enabled = True
            db.session.commit()
            AuditService.log(current_user.id, "Two-factor authentication enabled", "User", current_user.id)
            flash("Two-factor authentication is on.", "success")
            return redirect(url_for("admin.dashboard"))
        flash("That code is not correct. Scan the QR code again and enter the current code.", "error")

    return render_template("auth/setup_2fa.html", form=form, qr_base64=qr_base64,
                           secret=current_user.totp_secret)


@auth_bp.route("/2fa-disable", methods=["POST"])
@login_required
def disable_2fa():
    if current_user.role == "admin":
        current_user.totp_enabled = False
        current_user.totp_secret = None
        db.session.commit()
        AuditService.log(current_user.id, "Two-factor authentication disabled", "User", current_user.id)
        flash("Two-factor authentication is off.", "success")
    return redirect(url_for("admin.dashboard"))
