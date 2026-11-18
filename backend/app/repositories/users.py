from sqlalchemy.orm import Session
from ..models import User
from ..auth import hash_password

def create_user(db: Session, email: str, password: str) -> User:
    hashed = hash_password(password)
    db_user = User(email=email, password_hash=hashed)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()

def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).first()

def get_all_users(db: Session) -> list[User]:
    return db.query(User).all()

def update_business_name(db: Session, user_id: int, business_name: str) -> User | None:
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.business_name = business_name
        db.commit()
        db.refresh(user)
    return user

def set_logo_path(db: Session, user_id: int, logo_path: str) -> User | None:
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.logo_path = logo_path
        db.commit()
        db.refresh(user)
    return user

def get_user_profile(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).first()
