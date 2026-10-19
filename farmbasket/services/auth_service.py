from farmbasket.repositories.locality_repository import LocalityRepository
from farmbasket.repositories.user_repository import UserRepository


class AuthService:

    @staticmethod
    def register(full_name, email, password, role, phone=None, locality_id=None, terms_accepted=False):
        """Returns (user, error_message)."""
        if role not in ("buyer", "farmer"):
            return None, "Invalid role selected."
        if not terms_accepted:
            return None, "You must accept the Terms and Privacy Policy."

        locality = LocalityRepository.get(locality_id)
        if not locality or not locality.is_active:
            return None, "Choose one of the areas we currently serve."

        if UserRepository.get_by_email(email):
            return None, "An account with this email already exists."

        user = UserRepository.create_user(
            full_name=full_name, email=email, password=password, role=role,
            phone=phone, locality_id=locality.id, terms_accepted=True,
        )
        return user, None

    @staticmethod
    def authenticate(email, password):
        """Returns (user, error_message). One generic message for both
        unknown email and wrong password, so accounts cannot be probed."""
        user = UserRepository.get_by_email(email)
        if not user or not user.check_password(password):
            return None, "Incorrect email or password."
        if not user.is_active:
            return None, "This account has been deactivated. Contact support."
        return user, None
