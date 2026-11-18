from pathlib import Path
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from ..models import Client, Invoice, Reminder, User
from ..auth import hash_password
from ..config import settings

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

def delete_user_and_data(db: Session, user: User) -> None:
    """Permanently delete a user and everything they own (reminders, invoices, clients, logo file).

    Bulk deletes in FK order (invoices -> clients is RESTRICT), committed atomically.
    """
    own_invoices = select(Invoice.id).where(Invoice.user_id == user.id)
    db.execute(delete(Reminder).where(Reminder.invoice_id.in_(own_invoices)))
    db.execute(delete(Invoice).where(Invoice.user_id == user.id))
    db.execute(delete(Client).where(Client.user_id == user.id))
    logo_path = user.logo_path
    db.execute(delete(User).where(User.id == user.id))
    db.commit()
    if logo_path:  # after the commit: a failed delete must not leave a half-deleted account
        logos_dir = Path(settings.logos_dir)
        (logos_dir / logo_path.split("/")[-1]).unlink(missing_ok=True)
