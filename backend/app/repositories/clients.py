from ..db import utcnow
from sqlalchemy.orm import Session
from ..models import Client, Invoice
from datetime import datetime

def create_client(db: Session, user_id: int, name: str, email: str | None = None,
                  company: str | None = None, notes: str | None = None,
                  phone: str | None = None) -> Client:
    db_client = Client(
        user_id=user_id,
        name=name,
        email=email,
        company=company,
        notes=notes,
        phone=phone,
        created_at=utcnow(),
        updated_at=utcnow()
    )
    db.add(db_client)
    db.commit()
    db.refresh(db_client)
    return db_client

def get_client_by_id(db: Session, client_id: int, user_id: int) -> Client | None:
    return db.query(Client).filter(Client.id == client_id, Client.user_id == user_id).first()

def get_clients_by_user(db: Session, user_id: int, skip: int = 0, limit: int = 100) -> list[Client]:
    return db.query(Client).filter(Client.user_id == user_id).offset(skip).limit(limit).all()

def update_client(db: Session, client: Client, name: str | None = None,
                  email: str | None = None, company: str | None = None,
                  notes: str | None = None, phone: str | None = None) -> Client:
    if name is not None:
        client.name = name
    if email is not None:
        client.email = email
    if company is not None:
        client.company = company
    if notes is not None:
        client.notes = notes
    if phone is not None:
        client.phone = phone
    client.updated_at = utcnow()
    db.commit()
    db.refresh(client)
    return client

def delete_client(db: Session, client: Client) -> None:
    # Business rule: reject if client has invoices
    if db.query(Invoice).filter(Invoice.client_id == client.id).first():
        raise ValueError("Cannot delete client with existing invoices")
    db.delete(client)
    db.commit()
