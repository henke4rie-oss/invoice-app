from ..db import utcnow
from sqlalchemy.orm import Session
from ..models import Reminder, Invoice
from datetime import datetime
from typing import Optional

def create_reminder(db: Session, invoice_id: int, sent_at: datetime,
                     channel: str = "email", status: str = "sent",
                     error: Optional[str] = None, link: Optional[str] = None) -> Reminder:
    db_reminder = Reminder(
        invoice_id=invoice_id,
        sent_at=sent_at,
        channel=channel,
        status=status,
        error=error,
        link=link,
        created_at=utcnow()
    )
    db.add(db_reminder)
    db.commit()
    db.refresh(db_reminder)
    return db_reminder

def get_reminders_by_invoice(db: Session, invoice_id: int, user_id: int) -> list[Reminder]:
    # Verify invoice belongs to user before returning reminders
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.user_id == user_id).first()
    if not invoice:
        return []
    return db.query(Reminder).filter(Reminder.invoice_id == invoice_id).all()

def get_reminders_by_user(db: Session, user_id: int, status: Optional[str] = None,
                          skip: int = 0, limit: int = 100) -> list[Reminder]:
    query = db.query(Reminder).join(Invoice).filter(Invoice.user_id == user_id)
    if status:
        query = query.filter(Reminder.status == status)
    return query.offset(skip).limit(limit).all()
