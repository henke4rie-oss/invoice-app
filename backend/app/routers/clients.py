from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from ..db import get_db
from ..schemas import ClientCreate, ClientOut, ClientUpdate
from ..services.invoice_service import get_invoice_detail, list_invoices, update_invoice, transition_invoice_status, mark_overdue_if_needed
from ..deps import get_current_user
from ..models import User, Client
from typing import List, Optional

router = APIRouter()

# Client endpoints
@router.post("", status_code=status.HTTP_201_CREATED, response_model=ClientOut)
def create_client(
    client_data: ClientCreate, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    from ..repositories.clients import create_client
    try:
        client = create_client(db, current_user.id, client_data.name, client_data.email, 
                             client_data.company, client_data.notes, client_data.phone)
        return client
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("", response_model=List[ClientOut])
def list_clients(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100)
):
    from ..repositories.clients import get_clients_by_user
    clients = get_clients_by_user(db, current_user.id, skip=skip, limit=limit)
    return clients

@router.get("/{client_id}", response_model=ClientOut)
def get_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from ..repositories.clients import get_client_by_id
    client = get_client_by_id(db, client_id, current_user.id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client

@router.put("/{client_id}", response_model=ClientOut)
def update_client(
    client_id: int,
    client_data: ClientUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from ..repositories.clients import get_client_by_id, update_client
    client = get_client_by_id(db, client_id, current_user.id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    updated = update_client(db, client, client_data.name, client_data.email, 
                          client_data.company, client_data.notes, client_data.phone)
    return updated

@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from ..repositories.clients import get_client_by_id, delete_client
    client = get_client_by_id(db, client_id, current_user.id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    try:
        delete_client(db, client)
        return None
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
