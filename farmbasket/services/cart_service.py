from farmbasket.extensions import db
from farmbasket.models import CartItem, User
from farmbasket.repositories.product_repository import ProductRepository


def deliverable(buyer, product):
    """A buyer can only order from farmers who serve the buyer's own area."""
    return bool(buyer.locality_id and product.farmer.locality_id == buyer.locality_id)


class CartService:

    @staticmethod
    def get_cart_items(buyer_id):
        return CartItem.query.filter_by(buyer_id=buyer_id).order_by(CartItem.created_at.desc()).all()

    @staticmethod
    def cart_count(buyer_id):
        return CartItem.query.filter_by(buyer_id=buyer_id).count()

    @staticmethod
    def cart_total(buyer_id):
        return round(sum(item.subtotal for item in CartService.get_cart_items(buyer_id)), 2)

    @staticmethod
    def undeliverable_items(buyer, items=None):
        items = items if items is not None else CartService.get_cart_items(buyer.id)
        return [i for i in items if not deliverable(buyer, i.product)]

    @staticmethod
    def add_to_cart(buyer_id, product_id, quantity=1):
        buyer = db.session.get(User, buyer_id)
        product = ProductRepository.get_by_id(product_id)
        if not product or not product.in_stock:
            return None, "This product is not available right now."
        if not deliverable(buyer, product):
            return None, "This farmer does not deliver to your area."

        quantity = max(1, int(quantity or 1))
        existing = CartItem.query.filter_by(buyer_id=buyer_id, product_id=product_id).first()
        if existing:
            existing.quantity = min(existing.quantity + quantity, product.stock)
            db.session.commit()
            return existing, None

        item = CartItem(buyer_id=buyer_id, product_id=product_id, quantity=min(quantity, product.stock))
        db.session.add(item)
        db.session.commit()
        return item, None

    @staticmethod
    def increase_quantity(buyer_id, item_id):
        item = CartItem.query.filter_by(id=item_id, buyer_id=buyer_id).first()
        if item and item.quantity < item.product.stock:
            item.quantity += 1
            db.session.commit()
        return item

    @staticmethod
    def decrease_quantity(buyer_id, item_id):
        item = CartItem.query.filter_by(id=item_id, buyer_id=buyer_id).first()
        if not item:
            return None
        if item.quantity > 1:
            item.quantity -= 1
            db.session.commit()
            return item
        db.session.delete(item)
        db.session.commit()
        return None

    @staticmethod
    def remove_from_cart(buyer_id, item_id):
        item = CartItem.query.filter_by(id=item_id, buyer_id=buyer_id).first()
        if item:
            db.session.delete(item)
            db.session.commit()
            return True
        return False

    @staticmethod
    def clear_cart(buyer_id):
        CartItem.query.filter_by(buyer_id=buyer_id).delete()
        db.session.commit()
