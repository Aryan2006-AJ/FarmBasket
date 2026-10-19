from farmbasket.extensions import db
from farmbasket.models import User, utcnow


class UserRepository:

    @staticmethod
    def get_by_id(user_id):
        return db.session.get(User, int(user_id))

    @staticmethod
    def get_by_email(email):
        return User.query.filter_by(email=email.lower().strip()).first()

    @staticmethod
    def create_user(full_name, email, password, role, phone=None, locality_id=None, terms_accepted=False):
        user = User(
            full_name=full_name.strip(),
            email=email.lower().strip(),
            role=role,
            phone=phone.strip() if phone else None,
            locality_id=locality_id,
            terms_accepted_at=utcnow() if terms_accepted else None,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user

    @staticmethod
    def list_all():
        return User.query.order_by(User.created_at.desc()).all()

    @staticmethod
    def list_by_role(role):
        return User.query.filter_by(role=role).order_by(User.created_at.desc()).all()

    @staticmethod
    def count_by_role(role):
        return User.query.filter_by(role=role).count()

    @staticmethod
    def list_pending_kyc():
        return User.query.filter_by(role="farmer", kyc_status="Pending").order_by(User.kyc_submitted_at.asc()).all()

    @staticmethod
    def get_by_api_key(key):
        return User.query.filter_by(api_key=key).first()
