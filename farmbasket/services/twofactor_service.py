import pyotp


class TwoFactorService:

    @staticmethod
    def generate_secret():
        return pyotp.random_base32()

    @staticmethod
    def provisioning_uri(secret, email, issuer="FarmBasket"):
        return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)

    @staticmethod
    def verify(secret, code):
        if not secret or not code:
            return False
        try:
            return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)
        except Exception:
            return False
