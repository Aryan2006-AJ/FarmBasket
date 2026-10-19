from farmbasket.extensions import db
from farmbasket.models import Locality

DEFAULT_LOCALITIES = [
    ("Katraj", "Pune"), ("Kondhwa", "Pune"), ("Bibwewadi", "Pune"), ("Sinhagad Road", "Pune"),
    ("Kothrud", "Pune"), ("Warje", "Pune"), ("Baner", "Pune"), ("Aundh", "Pune"),
    ("Shivajinagar", "Pune"), ("Hadapsar", "Pune"), ("Viman Nagar", "Pune"), ("Wakad", "Pune"),
    ("Pimpri", "Pimpri-Chinchwad"), ("Chinchwad", "Pimpri-Chinchwad"), ("Akurdi", "Pimpri-Chinchwad"),
]


class LocalityRepository:

    @staticmethod
    def get(locality_id):
        if not locality_id:
            return None
        return db.session.get(Locality, int(locality_id))

    @staticmethod
    def list_active():
        return Locality.query.filter_by(is_active=True).order_by(Locality.city, Locality.name).all()

    @staticmethod
    def list_all():
        return Locality.query.order_by(Locality.city, Locality.name).all()

    @staticmethod
    def find(name, city):
        return Locality.query.filter(
            db.func.lower(Locality.name) == name.strip().lower(),
            db.func.lower(Locality.city) == city.strip().lower(),
        ).first()

    @staticmethod
    def create(name, city):
        locality = Locality(name=name.strip(), city=city.strip())
        db.session.add(locality)
        db.session.commit()
        return locality

    @staticmethod
    def toggle_active(locality):
        locality.is_active = not locality.is_active
        db.session.commit()
        return locality

    @staticmethod
    def seed_defaults_if_empty():
        if Locality.query.count() > 0:
            return 0
        for name, city in DEFAULT_LOCALITIES:
            db.session.add(Locality(name=name, city=city))
        db.session.commit()
        return len(DEFAULT_LOCALITIES)
