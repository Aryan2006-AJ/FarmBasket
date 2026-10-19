from sqlalchemy import func

from farmbasket.extensions import db
from farmbasket.models import OrderItem, Product, User


def _orderable(query, locality_id):
    query = query.filter(Product.is_available.is_(True), Product.stock > 0)
    if locality_id:
        query = query.join(User, Product.farmer_id == User.id).filter(User.locality_id == locality_id)
    return query


class RecommendationService:
    """Co-purchase suggestions from real order history, falling back to the
    same category. Only products orderable in the given area are returned."""

    @staticmethod
    def related_products(product_id, limit=4, locality_id=None):
        order_ids = [
            r[0] for r in db.session.query(OrderItem.order_id)
            .filter(OrderItem.product_id == product_id, OrderItem.status != "Cancelled").distinct().all()
        ]
        picked = []
        if order_ids:
            rows = (
                db.session.query(OrderItem.product_id, func.count(OrderItem.id))
                .filter(OrderItem.order_id.in_(order_ids), OrderItem.product_id != product_id,
                        OrderItem.status != "Cancelled")
                .group_by(OrderItem.product_id)
                .order_by(func.count(OrderItem.id).desc()).limit(limit * 3).all()
            )
            ids = [r[0] for r in rows]
            if ids:
                found = _orderable(Product.query.filter(Product.id.in_(ids)), locality_id).all()
                rank = {pid: i for i, pid in enumerate(ids)}
                picked = sorted(found, key=lambda p: rank[p.id])[:limit]

        if len(picked) >= limit:
            return picked

        current = db.session.get(Product, product_id)
        if not current:
            return picked
        exclude = {p.id for p in picked} | {product_id}
        fallback = (
            _orderable(Product.query.filter(Product.category == current.category, ~Product.id.in_(exclude)),
                       locality_id).limit(limit - len(picked)).all()
        )
        return picked + fallback

    @staticmethod
    def top_selling(limit=4, locality_id=None):
        rows = (
            db.session.query(OrderItem.product_id, func.sum(OrderItem.quantity))
            .filter(OrderItem.status != "Cancelled")
            .group_by(OrderItem.product_id)
            .order_by(func.sum(OrderItem.quantity).desc()).limit(limit * 4).all()
        )
        ids = [r[0] for r in rows]
        if not ids:
            return []
        found = _orderable(Product.query.filter(Product.id.in_(ids)), locality_id).all()
        rank = {pid: i for i, pid in enumerate(ids)}
        return sorted(found, key=lambda p: rank[p.id])[:limit]
