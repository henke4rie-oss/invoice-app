from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from ..db import get_db
from ..schemas import InvoiceCreate, InvoiceOut, InvoiceUpdate
from ..services.invoice_service import get_invoice_detail, list_invoices as list_invoices_service, update_invoice as update_invoice_service, transition_invoice_status, mark_overdue_if_needed
from ..deps import get_current_user
from ..models import User, Invoice, Client
from typing import List, Optional

router = APIRouter()


def _require_owned_client(db: Session, client_id: int, user_id: int) -> None:
    """404 (not 403) so we never confirm that another user's client exists."""
    from ..repositories.clients import get_client_by_id
    if not get_client_by_id(db, client_id, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")


# Invoice endpoints
@router.post("", status_code=status.HTTP_201_CREATED, response_model=InvoiceOut)
def create_invoice(
    invoice_data: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from ..repositories.invoices import create_invoice
    _require_owned_client(db, invoice_data.client_id, current_user.id)
    try:
        invoice = create_invoice(
            db,
            current_user.id,
            invoice_data.client_id,
            invoice_data.number,
            invoice_data.amount_cents,
            invoice_data.currency,
            invoice_data.issue_date,
            invoice_data.due_date,
            invoice_data.notes
        )
        return get_invoice_detail(db, invoice.id, current_user.id)
    except IntegrityError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Duplicate invoice number")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("", response_model=List[InvoiceOut])
def list_invoices(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    status: Optional[str] = None,
    client_id: Optional[int] = None,
    overdue: bool = False,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100)
):
    invoices = list_invoices_service(db, current_user.id, status=status, client_id=client_id, overdue=overdue, skip=skip, limit=limit)
    return invoices

@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    invoice = get_invoice_detail(db, invoice_id, current_user.id)
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return invoice

@router.put("/{invoice_id}", response_model=InvoiceOut)
def update_invoice(
    invoice_id: int,
    invoice_data: InvoiceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    changes = invoice_data.model_dump(exclude_unset=True)
    if changes.get("client_id") is not None:
        _require_owned_client(db, changes["client_id"], current_user.id)
    try:
        updated = update_invoice_service(db, invoice_id, current_user.id, **changes)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return updated

@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from ..repositories.invoices import get_invoice_by_id, delete_invoice
    invoice = get_invoice_by_id(db, invoice_id, current_user.id)
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    delete_invoice(db, invoice)
    return None

@router.patch("/{invoice_id}/status", response_model=InvoiceOut)
def update_invoice_status(
    invoice_id: int,
    status_update: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if "status" not in status_update:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing 'status' field")
    
    try:
        updated = transition_invoice_status(db, invoice_id, current_user.id, status_update["status"])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return updated

@router.get("/{invoice_id}/mark-overdue", response_model=InvoiceOut)
def mark_invoice_overdue(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    updated = mark_overdue_if_needed(db, invoice_id, current_user.id)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return updated
