from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, jsonify,
    send_from_directory, current_app, session, abort,
)
from flask_login import login_required, current_user

from farmbasket.extensions import db
from farmbasket.forms import LocalityChoiceForm
from farmbasket.repositories.locality_repository import LocalityRepository
from farmbasket.repositories.product_repository import ProductRepository
from farmbasket.services.cart_service import CartService
from farmbasket.services.recommendation_service import RecommendationService
from farmbasket.utils import role_required, safe_redirect_target

marketplace_bp = Blueprint("marketplace", __name__, url_prefix="/marketplace")


def delivery_locality():
    """The area whose farmers this visitor should see.
    Buyers: their saved area. Guests: the area they picked this session.
    Farmers and admins: none, they browse everything."""
    if current_user.is_authenticated:
        if current_user.role == "buyer":
            return current_user.locality
        return None
    return LocalityRepository.get(session.get("locality_id"))


@marketplace_bp.route("/")
def index():
    search = request.args.get("q", "").strip()
    category = request.args.get("category", "all")
    show_all = request.args.get("all") == "1"

    locality = None if show_all else delivery_locality()
    locality_id = locality.id if locality else None

    products = ProductRepository.list_available(search=search, category=category, locality_id=locality_id)
    unavailable = (ProductRepository.list_unavailable_in_locality(locality_id, search, category)
                   if locality_id else [])
    # A "most ordered" strip only helps when there is enough to choose from.
    popular = ([] if (search or category != "all" or len(products) < 8)
               else RecommendationService.top_selling(4, locality_id))

    elsewhere = 0
    if locality_id and not products and not search and category == "all":
        elsewhere = len(ProductRepository.list_available())

    buyer_locality_id = current_user.locality_id if (
        current_user.is_authenticated and current_user.role == "buyer") else None

    return render_template(
        "marketplace/index.html", products=products, unavailable=unavailable, popular=popular,
        categories=ProductRepository.list_categories(), search=search, selected_category=category,
        locality=locality, show_all=show_all, elsewhere=elsewhere, buyer_locality_id=buyer_locality_id,
        has_localities=bool(LocalityRepository.list_active()),
    )


@marketplace_bp.route("/set-area", methods=["GET", "POST"])
def set_locality():
    localities = LocalityRepository.list_active()
    form = LocalityChoiceForm()
    form.locality_id.choices = [(l.id, l.label) for l in localities]

    if request.method == "GET":
        current = delivery_locality()
        if current:
            form.locality_id.data = current.id

    if form.validate_on_submit():
        locality = LocalityRepository.get(form.locality_id.data)
        if not locality or not locality.is_active:
            flash("Choose one of the areas we serve.", "error")
        else:
            if current_user.is_authenticated and current_user.role == "buyer":
                current_user.locality_id = locality.id
                db.session.commit()
            elif not current_user.is_authenticated:
                session["locality_id"] = locality.id
            flash(f"Showing farmers who deliver to {locality.label}.", "success")
            return redirect(url_for("marketplace.index"))

    return render_template("marketplace/set_locality.html", form=form, has_localities=bool(localities))


@marketplace_bp.route("/api/search-suggestions")
def search_suggestions():
    locality = delivery_locality()
    return jsonify(ProductRepository.search_suggestions(
        request.args.get("q", ""), locality.id if locality else None))


@marketplace_bp.route("/product/<int:product_id>")
def product_detail(product_id):
    product = ProductRepository.get_by_id(product_id)
    if not product:
        abort(404)
    locality = delivery_locality()
    related = RecommendationService.related_products(product_id, 4, locality.id if locality else None)
    buyer_can_order = bool(
        current_user.is_authenticated and current_user.role == "buyer"
        and current_user.locality_id and current_user.locality_id == product.farmer.locality_id)
    return render_template("marketplace/product_detail.html", product=product, related=related,
                           buyer_can_order=buyer_can_order)


@marketplace_bp.route("/add-to-cart/<int:product_id>", methods=["POST"])
@login_required
@role_required("buyer")
def add_to_cart(product_id):
    quantity = request.form.get("quantity", 1, type=int) or 1
    item, error = CartService.add_to_cart(current_user.id, product_id, quantity)
    if error:
        flash(error, "error")
    else:
        flash(f"{item.product.name} is in your cart.", "success")
    return redirect(safe_redirect_target("marketplace.index"))


@marketplace_bp.route("/uploads/products/<path:filename>")
def product_image(filename):
    return send_from_directory(current_app.config["PRODUCT_IMAGE_FOLDER"], filename)
