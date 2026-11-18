from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from ..db import get_db
from ..schemas import ReminderOut, ReminderCreate
from ..services.reminder_service import send_reminder, trigger_overdue_reminders, ReminderLimitError
from ..deps import get_current_user
from ..models import User, Invoice, Reminder
from typing import List, Optional

router = APIRouter()

# Reminder endpoints
@router.get("/reminders", response_model=List[ReminderOut])
def list_reminders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    status: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100)
):
    from ..repositories.reminders import get_reminders_by_user
    reminders = get_reminders_by_user(db, current_user.id, status=status, skip=skip, limit=limit)
    return reminders

@router.post("/reminders/run-due", response_model=dict)
def run_due_reminders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = trigger_overdue_reminders(db, current_user.id)
    return result

# Invoice-specific reminders
@router.post("/invoices/{invoice_id}/reminders", status_code=status.HTTP_201_CREATED, response_model=ReminderOut)
def create_reminder_for_invoice(
    invoice_id: int,
    reminder_data: ReminderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        reminder = send_reminder(db, invoice_id, current_user.id, reminder_data.channel)
        return reminder
    except ReminderLimitError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))
    except ValueError as e:
        if "paid/cancelled" in str(e) or "paid" in str(e) or "cancelled" in str(e):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/invoices/{invoice_id}/reminders", response_model=List[ReminderOut])
def list_reminders_for_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    status: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100)
):
    from ..repositories.reminders import get_reminders_by_invoice
    reminders = get_reminders_by_invoice(db, invoice_id, current_user.id)
    
    if status:
        reminders = [r for r in reminders if r.status == status]
    
    return reminders[skip:skip + limit]

@router.get("/invoices/{invoice_id}/reminders/{reminder_id}", response_model=ReminderOut)
def get_reminder_for_invoice(
    invoice_id: int,
    reminder_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from ..repositories.reminders import get_reminders_by_invoice
    reminders = get_reminders_by_invoice(db, invoice_id, current_user.id)
    
    reminder = next((r for r in reminders if r.id == reminder_id), None)
    if not reminder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found")
    
    return reminder
