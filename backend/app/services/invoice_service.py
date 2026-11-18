from ..db import utcnow
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from ..repositories.invoices import get_invoice_by_id, update_invoice as update_invoice_record, update_invoice_status, get_invoices_by_user, check_transition
from ..repositories.clients import get_client_by_id
from ..models import Client
from datetime import datetime
from typing import Optional, List
from ..schemas import InvoiceOut

def get_invoice_detail(db: Session, invoice_id: int, user_id: int) -> InvoiceOut:
    invoice = get_invoice_by_id(db, invoice_id, user_id)
    if not invoice:
        return None
    # Join client name into response (client name only)
    client = db.query(Client).filter(Client.id == invoice.client_id).first()
    data = InvoiceOut.model_validate(invoice)
    data.client_name = client.name if client else None
    return data

def list_invoices(db: Session, user_id: int, status: Optional[str] = None,
                  client_id: Optional[int] = None, overdue: bool = False,
                  skip: int = 0, limit: int = 100) -> List[InvoiceOut]:
    invoices = get_invoices_by_user(db, user_id, status, client_id, overdue, skip, limit)
    # One batched lookup instead of one client query per invoice
    client_ids = {inv.client_id for inv in invoices}
    names = dict(db.query(Client.id, Client.name).filter(Client.id.in_(client_ids)).all()) if client_ids else {}
    result = []
    for inv in invoices:
        inv_data = InvoiceOut.model_validate(inv)
        inv_data.client_name = names.get(inv.client_id)
        result.append(inv_data)
    return result

def update_invoice(db: Session, invoice_id: int, user_id: int, **kwargs) -> InvoiceOut:
    invoice = get_invoice_by_id(db, invoice_id, user_id)
    if not invoice:
        return None
    new_status = kwargs.pop("status", None)
    if new_status is not None and new_status != invoice.status:
        check_transition(invoice.status, new_status)  # ValueError -> 409, nothing written yet
        kwargs["status"] = new_status
    try:
        updated = update_invoice_record(db, invoice, **kwargs)
    except IntegrityError:
        db.rollback()
        raise ValueError("Duplicate invoice number")
    return get_invoice_detail(db, updated.id, user_id)

def transition_invoice_status(db: Session, invoice_id: int, user_id: int, new_status: str) -> InvoiceOut:
    invoice = get_invoice_by_id(db, invoice_id, user_id)
    if not invoice:
        return None
    updated = update_invoice_status(db, invoice, new_status)
    return InvoiceOut.model_validate(updated)

def mark_overdue_if_needed(db: Session, invoice_id: int, user_id: int) -> InvoiceOut:
    invoice = get_invoice_by_id(db, invoice_id, user_id)
    if not invoice:
        return None
    if invoice.status in ("draft", "sent", "overdue") and invoice.due_date < utcnow():
        return transition_invoice_status(db, invoice_id, user_id, "overdue")
    return InvoiceOut.model_validate(invoice)
