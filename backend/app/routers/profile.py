from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from ..db import get_db
from ..schemas import AccountDelete, BusinessProfileOut, BusinessProfileUpdate
from ..auth import verify_password
from ..config import settings
from ..deps import get_current_user
from ..models import User
from pathlib import Path
import os

router = APIRouter()

@router.get("")
def get_user_profile_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from ..repositories.users import get_user_profile
    profile = get_user_profile(db, current_user.id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    logo_url = f"/api/profile/logo" if profile.logo_path else None
    return BusinessProfileOut(
        business_name=profile.business_name,
        logo_url=logo_url
    )

@router.put("")
def update_business_profile(
    profile_data: BusinessProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from ..repositories.users import update_business_name, get_user_profile
    if profile_data.business_name is not None:
        updated_user = update_business_name(db, current_user.id, profile_data.business_name)
        if not updated_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    profile = get_user_profile(db, current_user.id)
    logo_url = "/api/profile/logo" if profile.logo_path else None
    return BusinessProfileOut(
        business_name=profile.business_name,
        logo_url=logo_url
    )

@router.post("/logo")
async def upload_logo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from ..repositories.users import get_user_by_id, get_user_profile, set_logo_path
    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be an image")

    file_size = 0
    content = await file.read()
    file_size = len(content)
    if file_size > 2 * 1024 * 1024:  # 2MB
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File size must be <= 2MB")

    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    file_extension = file.filename.split('.')[-1].lower() if file.filename else ''
    if file_extension not in allowed_extensions:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File type not allowed")

    magic_bytes = content[:12]
    if file_extension == 'png':
        if magic_bytes[:8] != b'\x89PNG\r\n\x1a\n':
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid PNG file")
    elif file_extension in ['jpg', 'jpeg']:
        if magic_bytes[:2] != b'\xff\xd8':
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JPEG file")
    elif file_extension == 'gif':
        if magic_bytes[:6] not in [b'GIF87a', b'GIF89a']:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid GIF file")
    elif file_extension == 'webp':
        if magic_bytes[:4] != b'RIFF':
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid WebP file")

    logos_dir = Path(settings.logos_dir)
    logos_dir.mkdir(parents=True, exist_ok=True)

    safe_filename = f"{current_user.id}.{file_extension}"
    file_path = logos_dir / safe_filename

    with open(file_path, "wb") as f:
        f.write(content)

    logo_path = f"logos/{safe_filename}"
    updated_user = set_logo_path(db, current_user.id, logo_path)

    profile = get_user_profile(db, current_user.id)
    return BusinessProfileOut(
        business_name=profile.business_name,
        logo_url=f"/api/profile/logo" if profile.logo_path else None
    )

@router.get("/logo")
def get_logo(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from ..repositories.users import get_user_profile
    profile = get_user_profile(db, current_user.id)
    if not profile or not profile.logo_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Logo not found")

    # Extract filename from path
    filename = profile.logo_path.split('/')[-1]
    logos_dir = Path(settings.logos_dir)
    file_path = logos_dir / filename

    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Logo file not found")
    return FileResponse(file_path)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    data: AccountDelete,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Permanently delete the account and all of its data. Requires the current password."""
    from ..repositories.users import delete_user_and_data
    if current_user.is_demo:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="The demo account cannot be deleted")
    # 403 not 401: the frontend treats a 401 on this route as an expired session
    if not verify_password(current_user.password_hash, data.password):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Incorrect password")
    delete_user_and_data(db, current_user)
