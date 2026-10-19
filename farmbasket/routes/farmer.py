from collections import defaultdict
from datetime import timedelta

from flask import Blueprint, render_template, redirect, url_for, flash, jsonify, current_app, abort
from flask_login import login_required, current_user
from sqlalchemy import func

from farmbasket.extensions import db
from farmbasket.forms import ProductForm, KYCUploadForm
from farmbasket.models import OrderItem, FarmerPayout, PROGRESS, utcnow
from farmbasket.repositories.order_repository import OrderRepository
from farmbasket.repositories.product_repository import ProductRepository
from farmbasket.services.order_service import OrderService
from farmbasket.utils import role_required, save_uploaded_document

farmer_bp = Blueprint("farmer", __name__, url_prefix="/farmer")


def _own_product_or_404(product_id):
    product = ProductRepository.get_by_id(product_id)
    if not product or product.farmer_id != current_user.id:
        abort(404)
    return product


@farmer_bp.route("/dashboard")
@login_required
@role_required("farmer")
def dashboard():
    products = ProductRepository.list_by_farmer(current_user.id)
    return render_template(
        "farmer/dashboard.html",
        total_products=len(products),
        total_stock=sum(p.stock for p in products),
        active_listings=sum(1 for p in products if p.in_stock),
        low_stock=[p for p in products if p.is_available and 0 < p.stock <= 5],
        stats=OrderService.farmer_stats(current_user.id),
        recent_items=OrderRepository.list_items_for_farmer(current_user.id)[:5],
    )


@farmer_bp.route("/verification", methods=["GET", "POST"])
@login_required
@role_required("farmer")
def verification():
    form = KYCUploadForm()
    if current_user.kyc_status != "Approved" and form.validate_on_submit():
        filename = save_uploaded_document(form.document.data, current_app.config["KYC_DOC_FOLDER"])
        if not filename:
            flash("That file type is not allowed.", "error")
        else:
            current_user.kyc_document = filename
            current_user.kyc_status = "Pending"
            current_user.kyc_submitted_at = utcnow()
            current_user.kyc_notes = None
            db.session.commit()
            flash("Document submitted. An admin will review it.", "success")
            return redirect(url_for("farmer.verification"))
    return render_template("farmer/verification.html", form=form)


# Products

@farmer_bp.route("/products")
@login_required
@role_required("farmer")
def products():
    return render_template("farmer/products.html", products=ProductRepository.list_by_farmer(current_user.id))


@farmer_bp.route("/products/add", methods=["GET", "POST"])
@login_required
@role_required("farmer")
def add_product():
    form = ProductForm()
    if form.validate_on_submit():
        product = ProductRepository.create(current_user.id, form)
        flash(f"{product.name} is listed.", "success")
        return redirect(url_for("farmer.products"))
    return render_template("farmer/product_form.html", form=form, mode="add", product=None)


@farmer_bp.route("/products/edit/<int:product_id>", methods=["GET", "POST"])
@login_required
@role_required("farmer")
def edit_product(product_id):
    product = _own_product_or_404(product_id)
    form = ProductForm(obj=product)
    if form.validate_on_submit():
        ProductRepository.update(product, form)
        flash(f"{product.name} is updated.", "success")
        return redirect(url_for("farmer.products"))
    return render_template("farmer/product_form.html", form=form, mode="edit", product=product)


@farmer_bp.route("/products/delete/<int:product_id>", methods=["POST"])
@login_required
@role_required("farmer")
def delete_product(product_id):
    product = _own_product_or_404(product_id)
    name = product.name
    if product.order_items or product.reviews:
        # Past orders and reviews refer to this product, so it is unlisted instead.
        product.is_available = False
        db.session.commit()
        flash(f"{name} has past orders, so it was unlisted instead of deleted.", "success")
    else:
        ProductRepository.delete(product)
        flash(f"{name} was deleted.", "success")
    return redirect(url_for("farmer.products"))


# Orders

@farmer_bp.route("/orders")
@login_required
@role_required("farmer")
def orders():
    return render_template("farmer/orders.html", items=OrderRepository.list_items_for_farmer(current_user.id),
                           progress=PROGRESS)


@farmer_bp.route("/orders/<int:item_id>/advance", methods=["POST"])
@login_required
@role_required("farmer")
def advance_order_item(item_id):
    item = OrderItem.query.filter_by(id=item_id, farmer_id=current_user.id).first()
    if not item:
        abort(404)
    ok, message = OrderService.advance_item(item)
    flash(message, "success" if ok else "error")
    return redirect(url_for("farmer.orders"))


@farmer_bp.route("/earnings")
@login_required
@role_required("farmer")
def earnings():
    payouts = FarmerPayout.query.filter_by(farmer_id=current_user.id).order_by(FarmerPayout.created_at.desc()).all()
    return render_template("farmer/earnings.html", stats=OrderService.farmer_stats(current_user.id),
                           payouts=payouts)


# Analytics

@farmer_bp.route("/analytics")
@login_required
@role_required("farmer")
def analytics():
    return render_template("farmer/analytics.html")


@farmer_bp.route("/api/analytics/revenue-trend")
@login_required
@role_required("farmer")
def api_revenue_trend():
    buckets = defaultdict(float)
    for item in OrderItem.query.filter_by(farmer_id=current_user.id).all():
        if item.status != "Cancelled" and item.order:
            buckets[item.order.created_at.strftime("%Y-%m-%d")] += item.subtotal
    today = utcnow().date()
    days = [today - timedelta(days=d) for d in range(13, -1, -1)]
    return jsonify({"labels": [d.strftime("%d %b") for d in days],
                    "values": [round(buckets.get(d.strftime("%Y-%m-%d"), 0), 2) for d in days]})


@farmer_bp.route("/api/analytics/top-products")
@login_required
@role_required("farmer")
def api_top_products():
    rows = (
        db.session.query(OrderItem.product_name, func.sum(OrderItem.quantity))
        .filter(OrderItem.farmer_id == current_user.id, OrderItem.status != "Cancelled")
        .group_by(OrderItem.product_name).order_by(func.sum(OrderItem.quantity).desc()).limit(6).all()
    )
    return jsonify({"labels": [r[0] for r in rows], "values": [int(r[1]) for r in rows]})
