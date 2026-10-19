"""JSON API, v1. Authenticated with a personal key sent in the X-API-Key header.
Create a key on the Developer API page after logging in."""
from flask import Blueprint, jsonify, request

from farmbasket.extensions import limiter
from farmbasket.repositories.order_repository import OrderRepository
from farmbasket.repositories.product_repository import ProductRepository
from farmbasket.utils import api_key_required

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")


def _product_json(p):
    return {
        "id": p.id, "name": p.name, "category": p.category, "description": p.description,
        "price": p.price, "unit": p.unit, "stock": p.stock, "freshness": p.freshness,
        "in_stock": p.in_stock, "average_rating": p.avg_rating,
        "farmer": {"id": p.farmer.id, "name": p.farmer.full_name,
                   "area": p.farmer.locality.label if p.farmer.locality else None,
                   "verified": p.farmer.is_verified_farmer},
    }


def _order_json(o):
    return {
        "order_number": o.order_number, "total_amount": o.total_amount, "status": o.status,
        "payment_method": o.payment_method, "payment_status": o.payment_status,
        "delivery_window": o.delivery_slot, "placed_at": o.created_at.isoformat(),
        "items": [{"product": i.product_name, "price": i.price, "quantity": i.quantity,
                   "subtotal": i.subtotal, "status": i.status} for i in o.items],
    }


@api_bp.route("/products")
@limiter.limit("60 per minute")
@api_key_required
def list_products():
    user = request.api_user
    locality_id = user.locality_id if user.role == "buyer" else None
    products = ProductRepository.list_available(
        search=request.args.get("q"), category=request.args.get("category"), locality_id=locality_id)
    return jsonify({"count": len(products), "products": [_product_json(p) for p in products]})


@api_bp.route("/products/<int:product_id>")
@limiter.limit("60 per minute")
@api_key_required
def get_product(product_id):
    product = ProductRepository.get_by_id(product_id)
    if not product:
        return jsonify({"error": "Product not found."}), 404
    return jsonify(_product_json(product))


@api_bp.route("/orders")
@limiter.limit("60 per minute")
@api_key_required
def list_my_orders():
    user = request.api_user
    if user.role != "buyer":
        return jsonify({"error": "Only buyer accounts have orders here."}), 403
    orders = OrderRepository.list_by_buyer(user.id)
    return jsonify({"count": len(orders), "orders": [_order_json(o) for o in orders]})


@api_bp.route("/me")
@limiter.limit("60 per minute")
@api_key_required
def me():
    u = request.api_user
    return jsonify({"id": u.id, "name": u.full_name, "email": u.email, "role": u.role,
                    "area": u.locality.label if u.locality else None, "loyalty_points": u.loyalty_points})
