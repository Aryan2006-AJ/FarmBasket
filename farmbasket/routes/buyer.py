from flask import (
    Blueprint, render_template, redirect, url_for, flash, request, Response, jsonify, current_app, abort,
)
from flask_login import login_required, current_user

from farmbasket.extensions import db
from farmbasket.forms import CheckoutForm, ReviewForm
from farmbasket.models import Wishlist, Review
from farmbasket.repositories.order_repository import OrderRepository
from farmbasket.repositories.product_repository import ProductRepository
from farmbasket.services.cart_service import CartService
from farmbasket.services.coupon_service import CouponService
from farmbasket.services.invoice_service import InvoiceService
from farmbasket.services.loyalty_service import LoyaltyService
from farmbasket.services.order_service import OrderService
from farmbasket.utils import role_required, safe_redirect_target

buyer_bp = Blueprint("buyer", __name__, url_prefix="/buyer")


def _own_order_or_404(order_id):
    order = OrderRepository.get_by_id(order_id)
    if not order or order.buyer_id != current_user.id:
        abort(404)
    return order


@buyer_bp.route("/dashboard")
@login_required
@role_required("buyer")
def dashboard():
    orders = OrderRepository.list_by_buyer(current_user.id)
    return render_template(
        "buyer/dashboard.html",
        order_count=len(orders),
        active_orders=sum(1 for o in orders if o.status not in ("Delivered", "Cancelled")),
        cart_count=CartService.cart_count(current_user.id),
        wishlist_count=Wishlist.query.filter_by(buyer_id=current_user.id).count(),
        lifetime_spend=round(sum(o.total_amount for o in orders if o.status != "Cancelled"), 2),
        recent_orders=orders[:5],
    )


# Cart

@buyer_bp.route("/cart")
@login_required
@role_required("buyer")
def cart():
    items = CartService.get_cart_items(current_user.id)
    blocked_ids = {i.id for i in CartService.undeliverable_items(current_user, items)}
    return render_template("buyer/cart.html", items=items, total=CartService.cart_total(current_user.id),
                           blocked_ids=blocked_ids)


@buyer_bp.route("/cart/increase/<int:item_id>", methods=["POST"])
@login_required
@role_required("buyer")
def increase_quantity(item_id):
    CartService.increase_quantity(current_user.id, item_id)
    return redirect(url_for("buyer.cart"))


@buyer_bp.route("/cart/decrease/<int:item_id>", methods=["POST"])
@login_required
@role_required("buyer")
def decrease_quantity(item_id):
    CartService.decrease_quantity(current_user.id, item_id)
    return redirect(url_for("buyer.cart"))


@buyer_bp.route("/cart/remove/<int:item_id>", methods=["POST"])
@login_required
@role_required("buyer")
def remove_from_cart(item_id):
    CartService.remove_from_cart(current_user.id, item_id)
    flash("Item removed from your cart.", "success")
    return redirect(url_for("buyer.cart"))


# Checkout

@buyer_bp.route("/checkout", methods=["GET", "POST"])
@login_required
@role_required("buyer")
def checkout():
    items = CartService.get_cart_items(current_user.id)
    if not items:
        flash("Your cart is empty.", "error")
        return redirect(url_for("marketplace.index"))

    blocked = CartService.undeliverable_items(current_user, items)
    if blocked:
        flash("Some items in your cart are not delivered to your area. Remove them to continue.", "error")
        return redirect(url_for("buyer.cart"))

    total = CartService.cart_total(current_user.id)
    form = CheckoutForm()
    form.delivery_slot.choices = [(s, s) for s in current_app.config["DELIVERY_SLOTS"]]

    if request.method == "GET":
        form.delivery_name.data = current_user.full_name
        form.delivery_phone.data = current_user.phone
        form.delivery_city.data = current_user.locality.city if current_user.locality else ""

    if form.validate_on_submit():
        order, error = OrderService.place_order(
            current_user.id, form, coupon_code=form.coupon_code.data, redeem_points=form.redeem_points.data)
        if error:
            flash(error, "error")
        else:
            return redirect(url_for("buyer.order_confirmation", order_id=order.id))

    return render_template(
        "buyer/checkout.html", items=items, total=total, form=form,
        max_points=LoyaltyService.max_redeemable_points(current_user, total),
        point_value=LoyaltyService.point_value_rupees())


@buyer_bp.route("/checkout/validate-coupon", methods=["POST"])
@login_required
@role_required("buyer")
def validate_coupon():
    total = CartService.cart_total(current_user.id)
    coupon, discount, error = CouponService.validate_and_price(request.form.get("code", ""), total)
    if error:
        return jsonify({"valid": False, "message": error})
    return jsonify({"valid": True, "message": f"Coupon accepted. You save Rs. {discount:.2f}."})


@buyer_bp.route("/order/confirmation/<int:order_id>")
@login_required
@role_required("buyer")
def order_confirmation(order_id):
    order = _own_order_or_404(order_id)
    return render_template("buyer/order_confirmation.html", order=order,
                           qr_base64=InvoiceService.generate_order_qr_base64(order))


# Orders

@buyer_bp.route("/orders")
@login_required
@role_required("buyer")
def orders():
    return render_template("buyer/orders.html", orders=OrderRepository.list_by_buyer(current_user.id))


@buyer_bp.route("/orders/<int:order_id>")
@login_required
@role_required("buyer")
def order_detail(order_id):
    order = _own_order_or_404(order_id)
    reviewed = {r.product_id for r in Review.query.filter_by(order_id=order.id, buyer_id=current_user.id)}
    return render_template("buyer/order_detail.html", order=order, review_form=ReviewForm(),
                           reviewed=reviewed, qr_base64=InvoiceService.generate_order_qr_base64(order))


@buyer_bp.route("/orders/<int:order_id>/cancel", methods=["POST"])
@login_required
@role_required("buyer")
def cancel_order(order_id):
    order = _own_order_or_404(order_id)
    ok, error = OrderService.cancel_order(order)
    flash(f"Order {order.order_number} was cancelled." if ok else error, "success" if ok else "error")
    return redirect(url_for("buyer.order_detail", order_id=order.id))


@buyer_bp.route("/orders/<int:order_id>/invoice")
@login_required
@role_required("buyer")
def order_invoice(order_id):
    order = _own_order_or_404(order_id)
    return Response(
        InvoiceService.generate_invoice_pdf(order), mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=invoice_{order.order_number}.pdf"})


@buyer_bp.route("/orders/<int:order_id>/review/<int:product_id>", methods=["POST"])
@login_required
@role_required("buyer")
def submit_review(order_id, product_id):
    order = _own_order_or_404(order_id)
    in_order = any(i.product_id == product_id and i.status == "Delivered" for i in order.items)
    if not in_order:
        flash("You can review a product after it has been delivered.", "error")
        return redirect(url_for("buyer.order_detail", order_id=order.id))
    if Review.query.filter_by(order_id=order.id, product_id=product_id).first():
        flash("You already reviewed this product for this order.", "error")
        return redirect(url_for("buyer.order_detail", order_id=order.id))

    form = ReviewForm()
    if form.validate_on_submit():
        db.session.add(Review(buyer_id=current_user.id, product_id=product_id, order_id=order.id,
                              rating=int(form.rating.data), comment=(form.comment.data or "").strip() or None))
        db.session.commit()
        flash("Thanks, your review is saved.", "success")
    else:
        flash("Your review could not be saved.", "error")
    return redirect(url_for("buyer.order_detail", order_id=order.id))


# Wishlist

@buyer_bp.route("/wishlist")
@login_required
@role_required("buyer")
def wishlist():
    items = Wishlist.query.filter_by(buyer_id=current_user.id).order_by(Wishlist.created_at.desc()).all()
    return render_template("buyer/wishlist.html", items=items)


@buyer_bp.route("/wishlist/add/<int:product_id>", methods=["POST"])
@login_required
@role_required("buyer")
def add_to_wishlist(product_id):
    product = ProductRepository.get_by_id(product_id)
    if not product:
        abort(404)
    if Wishlist.query.filter_by(buyer_id=current_user.id, product_id=product_id).first():
        flash("Already in your wishlist.", "success")
    else:
        db.session.add(Wishlist(buyer_id=current_user.id, product_id=product_id))
        db.session.commit()
        flash(f"{product.name} saved to your wishlist.", "success")
    return redirect(safe_redirect_target("marketplace.index"))


@buyer_bp.route("/wishlist/remove/<int:product_id>", methods=["POST"])
@login_required
@role_required("buyer")
def remove_from_wishlist(product_id):
    Wishlist.query.filter_by(buyer_id=current_user.id, product_id=product_id).delete()
    db.session.commit()
    flash("Removed from your wishlist.", "success")
    return redirect(url_for("buyer.wishlist"))


@buyer_bp.route("/loyalty")
@login_required
@role_required("buyer")
def loyalty():
    return render_template("buyer/loyalty.html", history=LoyaltyService.history(current_user.id),
                           points=current_user.loyalty_points or 0)
