from sqlalchemy.orm import Session
from ..repositories.users import create_user, get_user_by_email
from ..auth import verify_password
from ..auth import create_user_token
from .demo_service import DEMO_EMAIL

def register_user(db: Session, email: str, password: str):
    # The demo address is reserved, even before the demo account has been seeded
    if email.lower() == DEMO_EMAIL or get_user_by_email(db, email):
        raise ValueError("Registration failed")
    user = create_user(db, email, password)
    return user

def login_user(db: Session, email: str, password: str) -> str:
    user = get_user_by_email(db, email)
    if not user or not verify_password(user.password_hash, password):
        raise ValueError("Invalid credentials")
    return create_user_token(user)
