from ..db import utcnow
from abc import ABC, abstractmethod
from sqlalchemy.orm import Session
from ..repositories.reminders import create_reminder, get_reminders_by_invoice, get_reminders_by_user
from ..repositories.invoices import get_invoice_by_id, update_invoice_status, get_invoices_by_user
from ..models import Invoice, Reminder
from datetime import datetime
from typing import Optional, Tuple
from ..schemas import ReminderOut, ReminderCreate
from ..config import settings
import smtplib
from email.mime.text import MIMEText
import urllib.parse
import logging
from typing import Iterator

logger = logging.getLogger(__name__)

class Sender(ABC):
    @abstractmethod
    def send(self, invoice: Invoice, channel: str) -> Tuple[str, str, Optional[str]]:
        """Send reminder for invoice. Returns (status, error, link)."""
        pass

class LogSender(Sender):
    def send(self, invoice: Invoice, channel: str) -> Tuple[str, str, Optional[str]]:
        # No SMTP configured: nothing is delivered, so say so instead of pretending
        return ("sent", "Email delivery not configured (SMTP_HOST unset) - reminder logged only", None)

class SmtpSender(Sender):
    def __init__(self):
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.user = settings.smtp_user
        self.password = settings.smtp_pass
        self.from_email = settings.smtp_from
        self.use_tls = settings.smtp_use_tls

    def send(self, invoice: Invoice, channel: str) -> Tuple[str, str, Optional[str]]:
        client_email = invoice.client.email if invoice.client and invoice.client.email else None
        if not client_email:
            return ('failed', 'Client has no email', None)

        subject = f"Reminder: Invoice {invoice.number}"
        business_name = invoice.user.business_name or 'Your business'
        amount = f"{invoice.currency} {invoice.amount_cents / 100:.2f}"
        due_date = invoice.due_date.strftime("%Y-%m-%d")
        body = f"Dear {invoice.client.name},\n\n"
        body += f"This is a reminder from {business_name} regarding invoice {invoice.number} for {amount} due on {due_date}.\n"
        if invoice.notes:
            body += f"\nNotes: {invoice.notes}"
        body += "\n\nPlease pay at your earliest convenience.\nThank you!"

        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = self.from_email
        msg['To'] = client_email

        try:
            with smtplib.SMTP(self.host, self.port) as server:
                if self.use_tls:
                    server.starttls()
                if self.user and self.password:
                    server.login(self.user, self.password)
                server.send_message(msg)
            return ('sent', '', None)
        except Exception as e:
            return ('failed', str(e), None)

class WhatsAppSender(Sender):
    def send(self, invoice: Invoice, channel: str) -> Tuple[str, str, Optional[str]]:
        client_phone = invoice.client.phone if invoice.client and invoice.client.phone else None
        if not client_phone:
            return ('failed', 'Client has no phone number', None)

        business_name = invoice.user.business_name or 'Your business'
        amount = f"{invoice.currency} {invoice.amount_cents / 100:.2f}"
        due_date = invoice.due_date.strftime("%Y-%m-%d")
        message = f"Hi {invoice.client.name}, this is a reminder from {business_name} regarding invoice {invoice.number} for {amount} due on {due_date}. Please pay at your earliest convenience. Thank you!"

        # Remove any non-digit characters for phone number
        digits = ''.join(filter(str.isdigit, client_phone))
        encoded_message = urllib.parse.quote(message)
        link = f"https://wa.me/{digits}?text={encoded_message}"

        return ('sent', '', link)

def get_sender(channel: str = "email") -> Sender:
    if channel == 'email':
        if settings.smtp_host:
            return SmtpSender()
        else:
            return LogSender()
    elif channel == 'whatsapp':
        return WhatsAppSender()
    else:
        return LogSender()

def send_reminder(db: Session, invoice_id: int, user_id: int, channel: str = "email") -> ReminderOut:
    invoice = get_invoice_by_id(db, invoice_id, user_id)
    if not invoice:
        raise ValueError("Invoice not found or access denied")
    if invoice.status in ("paid", "cancelled"):
        raise ValueError("Cannot send reminder for paid/cancelled invoice")

    # Dedup: skip if this channel already sent a reminder today (failed/skipped attempts don't count)
    today_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    existing = db.query(Reminder).filter(
        Reminder.invoice_id == invoice_id,
        Reminder.channel == channel,
        Reminder.status == "sent",
        Reminder.sent_at >= today_start
    ).first()
    if existing:
        reminder = create_reminder(db, invoice_id, utcnow(), channel, "skipped", "Duplicate today", None)
        return ReminderOut.model_validate(reminder)

    # Send via sender
    sender = get_sender(channel)
    status, error, link = sender.send(invoice, channel)
    if status == "sent" and invoice.status == "draft":
        # Only drafts move to 'sent'; overdue invoices stay overdue (overdue->sent is not a valid transition)
        update_invoice_status(db, invoice, "sent")
    reminder = create_reminder(db, invoice_id, utcnow(), channel, status, error if error else None, link)
    return ReminderOut.model_validate(reminder)

def _iter_overdue_invoices(db: Session, user_id: int, page_size: int = 500) -> Iterator[Invoice]:
    """Yield every unpaid, past-due invoice for the user, one page at a time.

    The filter (draft/sent/overdue and due_date < now) also matches invoices that
    become 'overdue' while we iterate, so offset paging stays stable.
    """
    skip = 0
    while True:
        page = get_invoices_by_user(db, user_id, overdue=True, skip=skip, limit=page_size)
        if not page:
            return
        yield from page
        if len(page) < page_size:
            return
        skip += page_size

def trigger_overdue_reminders(db: Session, user_id: int) -> dict:
    processed = 0
    sent = 0
    skipped = 0
    for inv in _iter_overdue_invoices(db, user_id):
        try:
            if inv.status != "overdue":
                update_invoice_status(db, inv, "overdue")
            rem = send_reminder(db, inv.id, user_id, "email")
            processed += 1
            if rem.status == "sent":
                sent += 1
            elif rem.status == "skipped":
                skipped += 1
        except Exception:
            db.rollback()
            logger.exception("Reminder failed for invoice %s (user %s)", inv.id, user_id)
    return {"processed": processed, "sent": sent, "skipped": skipped}
