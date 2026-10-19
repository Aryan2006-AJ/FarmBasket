"""Create an admin account. Admins cannot be created from the public sign-up form.

Usage:  python seed_admin.py
"""
import getpass

from farmbasket import create_app
from farmbasket.repositories.user_repository import UserRepository

app = create_app()

with app.app_context():
    print("Create admin account")
    full_name = input("Full name: ").strip() or "Administrator"
    email = input("Email: ").strip().lower()
    if not email:
        raise SystemExit("Email is required.")
    if UserRepository.get_by_email(email):
        raise SystemExit(f"An account with {email} already exists.")

    password = getpass.getpass("Password (8 characters or more): ")
    if len(password) < 8:
        raise SystemExit("Password must be at least 8 characters.")
    if password != getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords do not match.")

    admin = UserRepository.create_user(full_name=full_name, email=email, password=password, role="admin")
    print(f"Admin created: {admin.email}")
    print("Log in at /auth/login. Turn on two-factor authentication at /auth/2fa-setup.")
