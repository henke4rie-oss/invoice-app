import calendar
from .db import utcnow
from datetime import datetime, timedelta
from jose import JWTError
from jose.jwt import decode, encode
from .config import settings
import bcrypt

SECRET_KEY = settings.secret_key
ALGORITHM = "HS256"

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_password(hashed_password: str, plain_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = utcnow() + expires_delta
    else:
        expire = utcnow() + timedelta(minutes=settings.access_token_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt = encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def user_stamp(user) -> int:
    """Identity stamp of an account: its creation time in microseconds since the epoch (UTC).

    Bound into every token (claim "uat"). A database may hand a deleted user's id to a new account;
    the new account has a different creation time, so the old user's token no longer matches it.
    """
    created = user.created_at
    return calendar.timegm(created.utctimetuple()) * 1_000_000 + created.microsecond

def create_user_token(user) -> str:
    return create_access_token({"sub": str(user.id), "uat": user_stamp(user)})

def verify_token(token: str) -> dict:
    try:
        payload = decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return {}
