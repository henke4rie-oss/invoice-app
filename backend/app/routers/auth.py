from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..db import get_db
from ..schemas import UserCreate, UserOut, Token
from ..auth import create_user_token
from ..config import settings
from ..services.auth_service import register_user, login_user
from ..services.demo_service import get_demo_user, reset_demo_data
from ..deps import get_current_user
from ..models import User

router = APIRouter()

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: Session = Depends(get_db)):
    try:
        user = register_user(db, data.email, data.password)
        token = create_user_token(user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"access_token": token, "token_type": "bearer"}

@router.post("/login")
def login(data: UserCreate, db: Session = Depends(get_db)):
    try:
        token = login_user(db, data.email, data.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    return {"access_token": token, "token_type": "bearer"}

@router.post("/demo")
def demo_login(db: Session = Depends(get_db)):
    """Token for the shared demo account (created on first use if startup seeding did not run)."""
    if not settings.demo_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demo mode is disabled")
    try:
        user = get_demo_user(db) or reset_demo_data(db)
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    return {"access_token": create_user_token(user), "token_type": "bearer"}

@router.post("/demo/reset")
def demo_reset(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Restore the shared demo account to its pristine seed (the hourly job does the same)."""
    if not settings.demo_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demo mode is disabled")
    if not current_user.is_demo:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the demo account can be reset")
    reset_demo_data(db)
    return {"status": "reset"}

@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return UserOut(id=current_user.id, email=current_user.email, is_demo=current_user.is_demo,
                   created_at=current_user.created_at)
