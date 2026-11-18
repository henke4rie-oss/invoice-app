from ..db import utcnow
from sqlalchemy.orm import Session
from ..models import Invoice, Client, Reminder
from datetime import datetime
from typing import Optional

def create_invoice(db: Session, user_id: int, client_id: int, number: str,
                   amount_cents: int, currency: str, issue_date: datetime,
                   due_date: datetime, notes: Optional[str] = None) -> Invoice:
    db_invoice = Invoice(
        user_id=user_id,
        client_id=client_id,
        number=number,
        amount_cents=amount_cents,
        currency=currency,
        issue_date=issue_date,
        due_date=due_date,
        notes=notes,
        status="draft",
        created_at=utcnow(),
        updated_at=utcnow()
    )
    db.add(db_invoice)
    db.commit()
    db.refresh(db_invoice)
    return db_invoice

def get_invoice_by_id(db: Session, invoice_id: int, user_id: int) -> Invoice | None:
    return db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.user_id == user_id).first()

def get_invoices_by_user(db: Session, user_id: int, status: Optional[str] = None,
                         client_id: Optional[int] = None, overdue: bool = False,
                         skip: int = 0, limit: int = 100) -> list[Invoice]:
    query = db.query(Invoice).filter(Invoice.user_id == user_id)
    if status:
        query = query.filter(Invoice.status == status)
    if client_id:
        query = query.filter(Invoice.client_id == client_id)
    if overdue:
        query = query.filter(Invoice.status.in_(("sent", "draft", "overdue")))
        query = query.filter(Invoice.due_date < utcnow())
    return query.offset(skip).limit(limit).all()

def update_invoice(db: Session, invoice: Invoice, client_id: Optional[int] = None,
                   number: Optional[str] = None, amount_cents: Optional[int] = None,
                   currency: Optional[str] = None, issue_date: Optional[datetime] = None,
                   due_date: Optional[datetime] = None, notes: Optional[str] = None,
                   status: Optional[str] = None) -> Invoice:
    if client_id is not None:
        invoice.client_id = client_id
    if number is not None:
        invoice.number = number
    if amount_cents is not None:
        invoice.amount_cents = amount_cents
    if currency is not None:
        invoice.currency = currency.upper()
    if issue_date is not None:
        invoice.issue_date = issue_date
    if due_date is not None:
        invoice.due_date = due_date
    if notes is not None:
        invoice.notes = notes
    if status is not None:
        invoice.status = status
    invoice.updated_at = utcnow()
    db.commit()
    db.refresh(invoice)
    return invoice

def delete_invoice(db: Session, invoice: Invoice) -> None:
    # Deleting a invoice will cascade reminders and must ensure client deletion not blocked
    db.delete(invoice)
    db.commit()

ALLOWED_TRANSITIONS = {
    "draft": ["sent", "paid", "cancelled", "overdue"],
    "sent": ["paid", "overdue", "cancelled"],
    "overdue": ["paid", "cancelled"],
}

def check_transition(current: str, new_status: str) -> None:
    if new_status not in ALLOWED_TRANSITIONS.get(current, []):
        raise ValueError(f"Invalid status transition from {current} to {new_status}")

def update_invoice_status(db: Session, invoice: Invoice, new_status: str) -> Invoice:
    check_transition(invoice.status, new_status)
    invoice.status = new_status
    invoice.updated_at = utcnow()
    db.commit()
    db.refresh(invoice)
    return invoice
