from sqlalchemy.orm import Session
from ..repositories.users import create_user, get_user_by_email
from ..auth import verify_password
from ..auth import create_access_token

def register_user(db: Session, email: str, password: str):
    # Check if email already exists
    if get_user_by_email(db, email):
        raise ValueError("Registration failed")
    user = create_user(db, email, password)
    return user

def login_user(db: Session, email: str, password: str) -> str:
    user = get_user_by_email(db, email)
    if not user or not verify_password(user.password_hash, password):
        raise ValueError("Invalid credentials")
    token = create_access_token(data={"sub": str(user.id)})
    return token
