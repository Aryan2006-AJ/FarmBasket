import csv
import io

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request, Response, jsonify,
    send_from_directory, current_app, abort,
)
from flask_login import login_required, current_user
from sqlalchemy import func

from farmbasket.extensions import db
from farmbasket.forms import CouponForm, LocalityAdminForm
from farmbasket.models import (
    Coupon, FarmerPayout, Locality, Order, OrderItem, Payment, Product, User,
    ORDER_STATUSES, PRODUCT_CATEGORIES, utcnow,
)
from farmbasket.repositories.locality_repository import LocalityRepository
from farmbasket.repositories.order_repository import OrderRepository
from farmbasket.repositories.product_repository import ProductRepository
from farmbasket.repositories.user_repository import UserRepository
from farmbasket.scheduler import process_pending_payouts, send_low_stock_digest
from farmbasket.services.audit_service import AuditService
from farmbasket.services.coupon_service import CouponService
from farmbasket.services.notification_service import NotificationService
from farmbasket.services.order_service import OrderService
from farmbasket.utils import role_required

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _csv_cell(value):
    """Stop spreadsheet apps from running user text that starts with a formula character."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def _locality_stats(locality):
    farmers = User.query.filter_by(role="farmer", locality_id=locality.id).count()
    buyers = User.query.filter_by(role="buyer", locality_id=locality.id).count()
    listed = (db.session.query(func.count(Product.id)).join(User, Product.farmer_id == User.id)
              .filter(User.locality_id == locality.id).scalar() or 0)
    in_stock = (db.session.query(func.count(Product.id)).join(User, Product.farmer_id == User.id)
                .filter(User.locality_id == locality.id, Product.is_available.is_(True), Product.stock > 0)
                .scalar() or 0)
    orders = Order.query.filter(Order.locality_id == locality.id, Order.status != "Cancelled").all()
    return {
        "locality": locality, "farmers": farmers, "buyers": buyers, "listed": listed, "in_stock": in_stock,
        "orders": len(orders), "revenue": round(sum(o.total_amount for o in orders), 2),
    }


@admin_bp.route("/dashboard")
@login_required
@role_required("admin")
def dashboard():
    all_orders = OrderRepository.list_all()
    live = [o for o in all_orders if o.status != "Cancelled"]
    stats = {
        "buyers": UserRepository.count_by_role("buyer"),
        "farmers": UserRepository.count_by_role("farmer"),
        "products": Product.query.count(),
        "products_in_stock": Product.query.filter(Product.is_available.is_(True), Product.stock > 0).count(),
        "orders": len(all_orders),
        "active_orders": sum(1 for o in all_orders if o.status in ("Confirmed", "Packed", "Out for Delivery")),
        "delivered": sum(1 for o in all_orders if o.status == "Delivered"),
        "cancelled": sum(1 for o in all_orders if o.status == "Cancelled"),
        "order_value": round(sum(o.total_amount for o in live), 2),
        "payouts_paid": round(sum(p.amount for p in FarmerPayout.query.filter_by(status="Paid")), 2),
        "payouts_pending": round(sum(p.amount for p in FarmerPayout.query.filter_by(status="Pending")), 2),
        "pending_kyc": len(UserRepository.list_pending_kyc()),
    }
    rows = [_locality_stats(l) for l in LocalityRepository.list_all() if l.is_active]
    rows.sort(key=lambda r: (-(r["farmers"] + r["buyers"]), r["locality"].label))  # busiest areas first
    return render_template("admin/dashboard.html", stats=stats, rows=rows, recent_orders=all_orders[:8])


# Users

@admin_bp.route("/users")
@login_required
@role_required("admin")
def users():
    return render_template("admin/users.html", users=UserRepository.list_all())


@admin_bp.route("/users/<int:user_id>/toggle-active", methods=["POST"])
@login_required
@role_required("admin")
def toggle_user_active(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    if user.id == current_user.id:
        flash("You cannot deactivate your own account.", "error")
        return redirect(url_for("admin.users"))
    user.is_active = not user.is_active
    db.session.commit()
    AuditService.log(current_user.id, "Account activated" if user.is_active else "Account deactivated",
                     "User", user.id, user.email)
    flash(f"{user.full_name} is now {'active' if user.is_active else 'deactivated'}.", "success")
    return redirect(url_for("admin.users"))


# Farmers and verification

@admin_bp.route("/farmers")
@login_required
@role_required("admin")
def farmers():
    return render_template("admin/farmers.html", pending=UserRepository.list_pending_kyc(),
                           farmers=UserRepository.list_by_role("farmer"))


@admin_bp.route("/farmers/<int:user_id>/document")
@login_required
@role_required("admin")
def farmer_document(user_id):
    farmer = User.query.filter_by(id=user_id, role="farmer").first()
    if not farmer or not farmer.kyc_document:
        abort(404)
    return send_from_directory(current_app.config["KYC_DOC_FOLDER"], farmer.kyc_document)


@admin_bp.route("/farmers/<int:user_id>/verify", methods=["POST"])
@login_required
@role_required("admin")
def verify_farmer(user_id):
    farmer = User.query.filter_by(id=user_id, role="farmer").first()
    if not farmer:
        abort(404)
    decision = request.form.get("decision")
    if decision == "approve":
        farmer.kyc_status = "Approved"
        farmer.kyc_notes = None
        message = "Your farmer verification was approved."
        link = "/farmer/dashboard"
    elif decision == "reject":
        farmer.kyc_status = "Rejected"
        farmer.kyc_notes = (request.form.get("notes") or "").strip()[:255] or None
        message = "Your farmer verification was rejected. Check the note and submit again."
        link = "/farmer/verification"
    else:
        abort(400)
    farmer.kyc_reviewed_at = utcnow()
    db.session.commit()
    NotificationService.notify(farmer.id, message, category="system", link=link)
    AuditService.log(current_user.id, f"Verification {decision}d", "User", farmer.id, farmer.email)
    flash(f"{farmer.full_name}: verification {decision}d.", "success")
    return redirect(url_for("admin.farmers"))


# Localities

@admin_bp.route("/localities", methods=["GET", "POST"])
@login_required
@role_required("admin")
def localities():
    form = LocalityAdminForm()
    if form.validate_on_submit():
        if LocalityRepository.find(form.name.data, form.city.data):
            flash("That area already exists.", "error")
        else:
            locality = LocalityRepository.create(form.name.data, form.city.data)
            AuditService.log(current_user.id, "Area added", "Locality", locality.id, locality.label)
            flash(f"{locality.label} added.", "success")
            return redirect(url_for("admin.localities"))
    rows = [_locality_stats(l) for l in LocalityRepository.list_all()]
    return render_template("admin/localities.html", form=form, rows=rows)


@admin_bp.route("/localities/<int:locality_id>")
@login_required
@role_required("admin")
def locality_detail(locality_id):
    locality = LocalityRepository.get(locality_id)
    if not locality:
        abort(404)
    products = (Product.query.join(User, Product.farmer_id == User.id)
                .filter(User.locality_id == locality.id).order_by(Product.category, Product.name).all())
    available_categories = {p.category for p in products if p.in_stock}
    return render_template(
        "admin/locality_detail.html", stats=_locality_stats(locality), products=products,
        missing_categories=[c for c in PRODUCT_CATEGORIES if c not in available_categories],
        farmers=User.query.filter_by(role="farmer", locality_id=locality.id).all())


@admin_bp.route("/localities/<int:locality_id>/toggle", methods=["POST"])
@login_required
@role_required("admin")
def toggle_locality(locality_id):
    locality = LocalityRepository.get(locality_id)
    if not locality:
        abort(404)
    LocalityRepository.toggle_active(locality)
    AuditService.log(current_user.id, "Area opened" if locality.is_active else "Area closed",
                     "Locality", locality.id, locality.label)
    flash(f"{locality.label} is now {'open' if locality.is_active else 'closed'} for new sign-ups.", "success")
    return redirect(url_for("admin.localities"))


# Catalogue, orders, payments

@admin_bp.route("/products")
@login_required
@role_required("admin")
def products():
    return render_template("admin/products.html", products=ProductRepository.list_all())


@admin_bp.route("/orders")
@login_required
@role_required("admin")
def orders():
    return render_template("admin/orders.html", orders=OrderRepository.list_all())


@admin_bp.route("/payments")
@login_required
@role_required("admin")
def payments():
    return render_template(
        "admin/payments.html",
        payments=Payment.query.order_by(Payment.created_at.desc()).all(),
        payouts=FarmerPayout.query.order_by(FarmerPayout.created_at.desc()).all())


@admin_bp.route("/payouts/run-batch", methods=["POST"])
@login_required
@role_required("admin")
def run_payout_batch():
    settled = process_pending_payouts()
    AuditService.log(current_user.id, "Payout batch run", details=f"{settled} settled")
    flash(f"{settled} payout(s) settled.", "success")
    return redirect(url_for("admin.payments"))


@admin_bp.route("/payouts/run-stock-digest", methods=["POST"])
@login_required
@role_required("admin")
def run_stock_digest():
    count = send_low_stock_digest()
    flash(f"Low stock digest sent to {count} farmer(s).", "success")
    return redirect(url_for("admin.payments"))


# Coupons

@admin_bp.route("/coupons", methods=["GET", "POST"])
@login_required
@role_required("admin")
def coupons():
    form = CouponForm()
    if form.validate_on_submit():
        if CouponService.get_by_code(form.code.data):
            flash("A coupon with that code already exists.", "error")
        elif form.discount_type.data == "percent" and form.discount_value.data > 100:
            flash("A percentage discount cannot be more than 100.", "error")
        else:
            coupon = CouponService.create(form.code.data, form.discount_type.data, form.discount_value.data,
                                          form.min_order_amount.data, form.max_uses.data)
            AuditService.log(current_user.id, "Coupon created", "Coupon", coupon.id, coupon.code)
            flash(f"Coupon {coupon.code} created.", "success")
            return redirect(url_for("admin.coupons"))
    return render_template("admin/coupons.html", form=form, coupons=CouponService.list_all())


@admin_bp.route("/coupons/<int:coupon_id>/toggle", methods=["POST"])
@login_required
@role_required("admin")
def toggle_coupon(coupon_id):
    coupon = db.session.get(Coupon, coupon_id)
    if not coupon:
        abort(404)
    CouponService.toggle_active(coupon)
    AuditService.log(current_user.id, "Coupon toggled", "Coupon", coupon.id, coupon.code)
    flash(f"{coupon.code} is now {'active' if coupon.is_active else 'inactive'}.", "success")
    return redirect(url_for("admin.coupons"))


# Analytics

@admin_bp.route("/analytics")
@login_required
@role_required("admin")
def analytics():
    return render_template("admin/analytics.html")


@admin_bp.route("/api/analytics/revenue-trend")
@login_required
@role_required("admin")
def api_revenue_trend():
    series = OrderService.revenue_trend(days=14)
    return jsonify({"labels": [s[0] for s in series], "values": [s[1] for s in series]})


@admin_bp.route("/api/analytics/category-breakdown")
@login_required
@role_required("admin")
def api_category_breakdown():
    rows = (db.session.query(Product.category, func.sum(OrderItem.subtotal))
            .join(OrderItem, OrderItem.product_id == Product.id)
            .filter(OrderItem.status != "Cancelled").group_by(Product.category).all())
    return jsonify({"labels": [r[0] for r in rows], "values": [round(r[1], 2) for r in rows]})


@admin_bp.route("/api/analytics/order-status")
@login_required
@role_required("admin")
def api_order_status():
    counts = {s: 0 for s in ORDER_STATUSES}
    for o in OrderRepository.list_all():
        counts[o.status] = counts.get(o.status, 0) + 1
    return jsonify({"labels": list(counts.keys()), "values": list(counts.values())})


@admin_bp.route("/audit-log")
@login_required
@role_required("admin")
def audit_log():
    return render_template("admin/audit_log.html", logs=AuditService.recent(200))


# CSV exports

def _csv_response(filename, header, rows):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(header)
    for row in rows:
        writer.writerow([_csv_cell(c) for c in row])
    AuditService.log(current_user.id, f"Exported {filename}")
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


@admin_bp.route("/export/orders.csv")
@login_required
@role_required("admin")
def export_orders_csv():
    rows = [[o.order_number, o.buyer.full_name, o.locality.label if o.locality else "", o.total_amount,
             o.status, o.payment_method, o.payment_status, o.delivery_slot,
             o.created_at.strftime("%Y-%m-%d %H:%M")] for o in OrderRepository.list_all()]
    return _csv_response("orders.csv", ["Order", "Buyer", "Area", "Total", "Status", "Payment method",
                                        "Payment status", "Delivery window", "Placed"], rows)


@admin_bp.route("/export/users.csv")
@login_required
@role_required("admin")
def export_users_csv():
    rows = [[u.display_id, u.full_name, u.email, u.role, u.locality.label if u.locality else "",
             u.phone or "", u.is_active, u.created_at.strftime("%Y-%m-%d")] for u in UserRepository.list_all()]
    return _csv_response("users.csv", ["ID", "Name", "Email", "Role", "Area", "Phone", "Active", "Joined"], rows)
