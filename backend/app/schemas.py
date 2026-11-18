from datetime import datetime
from pydantic import BaseModel, EmailStr, ConfigDict, Field, field_validator
from typing import Literal, Optional

def _check_bcrypt_length(password: str) -> str:
    # bcrypt only accepts 72 bytes; multi-byte characters can exceed that within 72 characters
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Password must be at most 72 bytes")
    return password

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)

    _bcrypt_limit = field_validator("password")(_check_bcrypt_length)

class AccountDelete(BaseModel):
    password: str = Field(min_length=1, max_length=72)

    _bcrypt_limit = field_validator("password")(_check_bcrypt_length)

class UserOut(BaseModel):
    id: int
    email: EmailStr
    is_demo: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class ClientCreate(BaseModel):
    name: str = Field(max_length=120)
    phone: Optional[str] = Field(None, max_length=32)
    email: Optional[EmailStr] = None
    company: Optional[str] = None
    notes: Optional[str] = None

class ClientOut(ClientCreate):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ClientUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=120)
    phone: Optional[str] = Field(None, max_length=32)
    email: Optional[EmailStr] = None
    company: Optional[str] = Field(None, max_length=120)
    notes: Optional[str] = Field(None, max_length=2000)

    model_config = ConfigDict(from_attributes=True)

class InvoiceCreate(BaseModel):
    client_id: int
    number: str = Field(max_length=64)
    amount_cents: int = Field(gt=0, le=1000000000)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    issue_date: datetime
    due_date: datetime
    notes: Optional[str] = Field(None, max_length=2000)

    @field_validator("currency", mode="before")
    @classmethod
    def uppercase_currency(cls, v):
        return v.upper() if isinstance(v, str) else v

class InvoiceOut(InvoiceCreate):
    id: int
    user_id: int
    status: str
    created_at: datetime
    updated_at: datetime
    client_name: str | None = None

    model_config = ConfigDict(from_attributes=True)

class InvoiceUpdate(BaseModel):
    client_id: Optional[int] = None
    number: Optional[str] = Field(None, max_length=64)
    amount_cents: Optional[int] = Field(None, gt=0, le=1000000000)
    currency: Optional[str] = Field(None, pattern=r"^[A-Z]{3}$")
    issue_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    notes: Optional[str] = Field(None, max_length=2000)
    status: Optional[Literal["draft", "sent", "paid", "overdue", "cancelled"]] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("currency", mode="before")
    @classmethod
    def uppercase_currency(cls, v):
        return v.upper() if isinstance(v, str) else v

class ReminderOut(BaseModel):
    id: int
    invoice_id: int
    sent_at: datetime
    channel: str
    status: str
    error: Optional[str] = None
    link: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ReminderCreate(BaseModel):
    channel: Literal["email", "whatsapp"] = "email"

class BusinessProfileOut(BaseModel):
    business_name: Optional[str] = None
    logo_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class BusinessProfileUpdate(BaseModel):
    business_name: Optional[str] = Field(None, max_length=120)
