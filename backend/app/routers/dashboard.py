from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session
from ..db import get_db, utcnow
from ..deps import get_current_user
from ..models import User, Invoice, Client, Reminder
from datetime import timedelta
from typing import Dict, Any

router = APIRouter()

UNPAID_STATUSES = ("sent", "draft", "overdue")
CLOSED_STATUSES = ("paid", "cancelled")


@router.get("/", response_model=Dict[str, Any])
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    uid = current_user.id
    now = utcnow()
    week_ago = now - timedelta(days=7)

    # All counts/sums are computed in SQL: O(n) in the DB, O(1) rows in Python.
    total_clients = db.query(func.count(Client.id)).filter(Client.user_id == uid).scalar()
    total_invoices, total_cents = db.query(
        func.count(Invoice.id), func.coalesce(func.sum(Invoice.amount_cents), 0)
    ).filter(Invoice.user_id == uid).one()

    total_overdue = db.query(func.count(Invoice.id)).filter(
        Invoice.user_id == uid,
        Invoice.status.in_(UNPAID_STATUSES),
        Invoice.due_date < now,
    ).scalar()

    reminder_base = db.query(func.count(Reminder.id)).select_from(Reminder).join(
        Invoice, Invoice.id == Reminder.invoice_id
    ).filter(Invoice.user_id == uid)
    total_pending_reminders = reminder_base.filter(Reminder.status.in_(("sent", "skipped"))).scalar()
    recent_reminders_count = reminder_base.filter(Reminder.created_at >= week_ago).scalar()

    recent_invoices_count = db.query(func.count(Invoice.id)).filter(
        Invoice.user_id == uid, Invoice.created_at >= week_ago
    ).scalar()
    recent_clients_count = db.query(func.count(Client.id)).filter(
        Client.user_id == uid, Client.created_at >= week_ago
    ).scalar()

    # Latest 5 invoices from the last 7 days, client name joined in one query
    recent_rows = (
        db.query(Invoice, Client.name)
        .join(Client, Client.id == Invoice.client_id)
        .filter(Invoice.user_id == uid, Invoice.created_at >= week_ago)
        .order_by(Invoice.created_at.desc(), Invoice.id.desc())
        .limit(5)
        .all()
    )

    # Top 5 clients by billed amount, aggregated per client in a single GROUP BY
    top_rows = (
        db.query(
            Client.id,
            Client.name,
            Client.email,
            func.count(Invoice.id),
            func.coalesce(func.sum(Invoice.amount_cents), 0),
        )
        .outerjoin(Invoice, Invoice.client_id == Client.id)
        .filter(Client.user_id == uid)
        .group_by(Client.id)
        .order_by(func.coalesce(func.sum(Invoice.amount_cents), 0).desc(), Client.id)
        .limit(5)
        .all()
    )

    return {
        "total_clients": total_clients,
        "total_invoices": total_invoices,
        "total_amount": total_cents / 100.0,
        "total_overdue": total_overdue,
        "total_pending_reminders": total_pending_reminders,
        "recent_invoices_count": recent_invoices_count,
        "recent_clients_count": recent_clients_count,
        "recent_reminders_count": recent_reminders_count,
        "recent_invoices": [
            {
                "id": inv.id,
                "number": inv.number,
                "amount_cents": inv.amount_cents,
                "currency": inv.currency,
                "status": inv.status,
                "due_date": inv.due_date,
                "client_name": client_name,
            }
            for inv, client_name in recent_rows
        ],
        "top_clients": [
            {
                "id": cid,
                "name": name,
                "email": email,
                "invoice_count": count,
                "total_amount": cents / 100.0,
            }
            for cid, name, email, count, cents in top_rows
        ],
    }


@router.get("/summary", response_model=Dict[str, Any])
def get_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    uid = current_user.id
    now = utcnow()

    by_status = dict(
        db.query(Invoice.status, func.count(Invoice.id))
        .filter(Invoice.user_id == uid)
        .group_by(Invoice.status)
        .all()
    )

    outstanding_by_currency = dict(
        db.query(Invoice.currency, func.sum(Invoice.amount_cents))
        .filter(Invoice.user_id == uid, Invoice.status.notin_(CLOSED_STATUSES))
        .group_by(Invoice.currency)
        .all()
    )

    overdue_count = db.query(func.count(Invoice.id)).filter(
        Invoice.user_id == uid,
        Invoice.due_date < now,
        Invoice.status.notin_(CLOSED_STATUSES),
    ).scalar()

    reminders_sent_30d = db.query(func.count(Reminder.id)).select_from(Reminder).join(
        Invoice, Invoice.id == Reminder.invoice_id
    ).filter(
        Invoice.user_id == uid,
        Reminder.status == "sent",
        Reminder.created_at >= now - timedelta(days=30),
    ).scalar()

    return {
        "total_invoices": sum(by_status.values()),
        "by_status": by_status,
        "outstanding_by_currency": outstanding_by_currency,
        "overdue_count": overdue_count,
        "reminders_sent_30d": reminders_sent_30d,
    }
