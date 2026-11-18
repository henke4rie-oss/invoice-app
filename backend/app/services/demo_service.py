"""Demo mode: one shared, pre-filled account that anyone can enter with a click.

The demo user has a random, unrecoverable password (it can only be entered through
POST /api/auth/demo), never sends real email, and is re-seeded on a schedule.
"""
import logging
import secrets
import urllib.parse
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..auth import hash_password
from ..db import SessionLocal, utcnow
from ..models import Client, Invoice, Reminder, User

logger = logging.getLogger(__name__)

DEMO_EMAIL = "demo@example.com"
DEMO_BUSINESS_NAME = "Northwind Studio"

# (name, company, email, phone)
_CLIENTS = [
    ("Thandi Mokoena", "Bluegum Café", "thandi.mokoena@example.com", "+27 82 555 0101"),
    ("Liam van der Merwe", "Harbour Print Co.", "liam.vdm@example.org", "+27 83 555 0102"),
    ("Priya Naidoo", "Lotus Interiors", "priya.naidoo@example.net", "+27 84 555 0103"),
    ("Marc Dubois", "Atelier Dubois", "marc.dubois@example.com", "+33 6 55 55 01 04"),
    ("Zanele Khumalo", "Khumalo Logistics", "zanele@example.org", "+27 71 555 0105"),
    ("Ethan Brooks", "Brooks & Co. Legal", "ethan.brooks@example.net", "+1 415 555 0106"),
]

# (number, client index, amount_cents, currency, issued N days ago, due in N days (negative = past), status, notes)
_INVOICES = [
    ("DEMO-1001", 0, 1250000, "ZAR", 70, -40, "paid", "Brand identity refresh"),
    ("DEMO-1002", 1, 480000, "ZAR", 55, -25, "paid", "Flyer design and print run"),
    ("DEMO-1003", 2, 125000, "USD", 48, -18, "paid", "Showroom photography"),
    ("DEMO-1004", 3, 98000, "EUR", 40, -10, "paid", "Website copywriting"),
    ("DEMO-1005", 0, 820000, "ZAR", 35, -5, "overdue", "Menu and signage design"),
    ("DEMO-1006", 4, 1575000, "ZAR", 45, -15, "overdue", "Fleet livery artwork"),
    ("DEMO-1007", 2, 240000, "USD", 60, -30, "overdue", "Catalogue layout, 48 pages"),
    ("DEMO-1008", 5, 315000, "ZAR", 28, -2, "overdue", "Annual report formatting"),
    ("DEMO-1009", 1, 640000, "ZAR", 10, 20, "sent", "Packaging mock-ups"),
    ("DEMO-1010", 3, 175000, "EUR", 7, 23, "sent", "Social media templates"),
    ("DEMO-1011", 4, 990000, "ZAR", 5, 9, "sent", "Driver app UI design"),
    ("DEMO-1012", 5, 280000, "ZAR", 1, 29, "draft", None),
    ("DEMO-1013", 0, 560000, "ZAR", 0, 30, "draft", "Seasonal campaign"),
    ("DEMO-1014", 2, 64000, "USD", 0, 14, "draft", None),
    ("DEMO-1015", 1, 120000, "ZAR", 20, 10, "cancelled", "Project paused by client"),
]

# (invoice number, sent N days ago, channel, status, error)
_REMINDERS = [
    ("DEMO-1005", 3, "email", "sent", None),
    ("DEMO-1005", 2, "whatsapp", "sent", None),
    ("DEMO-1006", 10, "email", "sent", None),
    ("DEMO-1006", 4, "email", "sent", None),
    ("DEMO-1006", 1, "email", "skipped", "Duplicate today"),
    ("DEMO-1007", 20, "email", "sent", None),
    ("DEMO-1007", 6, "email", "sent", None),
    ("DEMO-1007", 1, "email", "failed", "Mailbox unavailable"),
    ("DEMO-1008", 1, "whatsapp", "sent", None),
]

_LOGOS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "logos"


def get_demo_user(db: Session) -> User | None:
    return db.query(User).filter(User.email == DEMO_EMAIL, User.is_demo.is_(True)).first()


def _wipe(db: Session, user: User) -> None:
    """Remove everything the demo user owns (bulk deletes: O(1) statements, not O(n) objects)."""
    own_invoices = select(Invoice.id).where(Invoice.user_id == user.id)
    db.execute(delete(Reminder).where(Reminder.invoice_id.in_(own_invoices)))
    db.execute(delete(Invoice).where(Invoice.user_id == user.id))
    db.execute(delete(Client).where(Client.user_id == user.id))
    if user.logo_path:
        (_LOGOS_DIR / user.logo_path.split("/")[-1]).unlink(missing_ok=True)
        user.logo_path = None


def reset_demo_data(db: Session) -> User:
    """Create the demo user if needed and restore its data to the pristine seed. Idempotent."""
    user = db.query(User).filter(User.email == DEMO_EMAIL).first()
    if user is not None and not user.is_demo:
        # A real account already owns this address: never touch it.
        raise RuntimeError("A regular account already uses the demo email; demo mode is unavailable")
    if user is None:
        user = User(email=DEMO_EMAIL, password_hash=hash_password(secrets.token_urlsafe(32)), is_demo=True)
        db.add(user)
        db.flush()

    _wipe(db, user)
    user.business_name = DEMO_BUSINESS_NAME

    now = utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    clients = [
        Client(user_id=user.id, name=name, company=company, email=email, phone=phone, created_at=now, updated_at=now)
        for name, company, email, phone in _CLIENTS
    ]
    db.add_all(clients)
    db.flush()

    invoices = {}
    for number, client_idx, amount, currency, issued_ago, due_in, status, notes in _INVOICES:
        issued = today - timedelta(days=issued_ago)
        invoices[number] = Invoice(
            user_id=user.id, client_id=clients[client_idx].id, number=number, amount_cents=amount,
            currency=currency, issue_date=issued, due_date=today + timedelta(days=due_in),
            status=status, notes=notes, created_at=issued, updated_at=issued,
        )
    db.add_all(invoices.values())
    db.flush()

    client_phone = {c.id: c.phone for c in clients}
    reminders = []
    for number, sent_ago, channel, status, error in _REMINDERS:
        invoice = invoices[number]
        link = None
        if channel == "whatsapp" and status == "sent":
            digits = "".join(ch for ch in client_phone[invoice.client_id] if ch.isdigit())
            text = urllib.parse.quote(f"Reminder: invoice {number} is overdue. Thank you!")
            link = f"https://wa.me/{digits}?text={text}"
        sent_at = now - timedelta(days=sent_ago)
        reminders.append(Reminder(invoice_id=invoice.id, sent_at=sent_at, channel=channel, status=status,
                                  error=error, link=link, created_at=sent_at))
    db.add_all(reminders)

    db.commit()
    db.refresh(user)
    return user


def ensure_demo_user() -> None:
    """Startup hook: seed the demo account if it does not exist yet."""
    db = SessionLocal()
    try:
        if get_demo_user(db) is None:
            reset_demo_data(db)
            logger.info("Seeded demo account")
    finally:
        db.close()


def reset_demo_job() -> None:
    """Scheduled hook: restore the demo account to its pristine state."""
    db = SessionLocal()
    try:
        reset_demo_data(db)
        logger.info("Demo account reset")
    except Exception:
        db.rollback()
        logger.exception("Demo reset failed")
    finally:
        db.close()
