from flask import current_app

from farmbasket.extensions import db
from farmbasket.models import Product, User, PRODUCT_CATEGORIES
from farmbasket.utils import save_uploaded_image


def _in_stock(query):
    return query.filter(Product.is_available.is_(True), Product.stock > 0)


def _in_locality(query, locality_id):
    return query.join(User, Product.farmer_id == User.id).filter(User.locality_id == locality_id)


class ProductRepository:

    @staticmethod
    def get_by_id(product_id):
        return db.session.get(Product, int(product_id))

    @staticmethod
    def list_available(search=None, category=None, locality_id=None):
        query = _in_stock(Product.query)
        if search:
            query = query.filter(Product.name.ilike(f"%{search.strip()}%"))
        if category and category != "all":
            query = query.filter(Product.category == category)
        if locality_id:
            query = _in_locality(query, locality_id)
        return query.order_by(Product.created_at.desc()).all()

    @staticmethod
    def list_unavailable_in_locality(locality_id, search=None, category=None):
        """Products listed by farmers in this area that cannot be ordered right now."""
        query = _in_locality(Product.query, locality_id).filter(
            db.or_(Product.is_available.is_(False), Product.stock <= 0)
        )
        if search:
            query = query.filter(Product.name.ilike(f"%{search.strip()}%"))
        if category and category != "all":
            query = query.filter(Product.category == category)
        return query.order_by(Product.updated_at.desc()).all()

    @staticmethod
    def search_suggestions(prefix, locality_id=None, limit=8):
        if not prefix or len(prefix.strip()) < 2:
            return []
        query = _in_stock(Product.query).filter(Product.name.ilike(f"%{prefix.strip()}%"))
        if locality_id:
            query = _in_locality(query, locality_id)
        rows = query.with_entities(Product.id, Product.name, Product.category).limit(limit).all()
        return [{"id": r[0], "name": r[1], "category": r[2]} for r in rows]

    @staticmethod
    def list_categories():
        return list(PRODUCT_CATEGORIES)

    @staticmethod
    def list_by_farmer(farmer_id):
        return Product.query.filter_by(farmer_id=farmer_id).order_by(Product.created_at.desc()).all()

    @staticmethod
    def list_all():
        return Product.query.order_by(Product.created_at.desc()).all()

    @staticmethod
    def create(farmer_id, form):
        image_file = None
        if form.photo.data:
            image_file = save_uploaded_image(form.photo.data, current_app.config["PRODUCT_IMAGE_FOLDER"])
        product = Product(
            farmer_id=farmer_id,
            name=form.name.data.strip(),
            category=form.category.data,
            description=(form.description.data or "").strip() or None,
            price=form.price.data,
            unit=form.unit.data,
            stock=form.stock.data or 0,
            freshness=(form.freshness.data or "").strip() or None,
            image_file=image_file,
            is_available=form.is_available.data,
        )
        db.session.add(product)
        db.session.commit()
        return product

    @staticmethod
    def update(product, form):
        product.name = form.name.data.strip()
        product.category = form.category.data
        product.description = (form.description.data or "").strip() or None
        product.price = form.price.data
        product.unit = form.unit.data
        product.stock = form.stock.data or 0
        product.freshness = (form.freshness.data or "").strip() or None
        product.is_available = form.is_available.data
        if form.photo.data:
            image_file = save_uploaded_image(form.photo.data, current_app.config["PRODUCT_IMAGE_FOLDER"])
            if image_file:
                product.image_file = image_file
        db.session.commit()
        return product

    @staticmethod
    def delete(product):
        db.session.delete(product)
        db.session.commit()
