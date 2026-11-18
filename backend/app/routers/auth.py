from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..db import get_db
from ..schemas import UserCreate, UserOut, Token
from ..services.auth_service import register_user, login_user
from ..deps import get_current_user
from ..models import User

router = APIRouter()

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: Session = Depends(get_db)):
    try:
        user = register_user(db, data.email, data.password)
        from ..auth import create_access_token
        from datetime import timedelta
        token = create_access_token({"sub": str(user.id)})
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

@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return UserOut(id=current_user.id, email=current_user.email, created_at=current_user.created_at)
