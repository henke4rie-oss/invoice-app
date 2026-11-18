from sqlalchemy import Boolean, Column, Integer, String, Text, DateTime, ForeignKey, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import expression
from .db import Base, utcnow

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    business_name = Column(String)
    logo_path = Column(String)
    is_demo = Column(Boolean, nullable=False, default=False, server_default=expression.false())
    created_at = Column(DateTime, default=utcnow, nullable=False)

    clients = relationship("Client", back_populates="user")
    invoices = relationship("Invoice", back_populates="user")

class Client(Base):
    __tablename__ = "clients"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    phone = Column(String)
    email = Column(String)
    company = Column(String)
    notes = Column(Text)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    user = relationship("User", back_populates="clients")
    invoices = relationship("Invoice", back_populates="client")

class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False, index=True)
    number = Column(String, nullable=False)
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String, nullable=False, default="USD")
    issue_date = Column(DateTime, nullable=False)
    due_date = Column(DateTime, nullable=False)
    status = Column(String, nullable=False, default="draft")
    notes = Column(Text)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('draft','sent','paid','overdue','cancelled')"),
        UniqueConstraint("user_id", "number", name="_user_number_uc"),
    )

    user = relationship("User", back_populates="invoices")
    client = relationship("Client", back_populates="invoices")
    reminders = relationship("Reminder", back_populates="invoice", cascade="all, delete-orphan")

class Reminder(Base):
    __tablename__ = "reminders"
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    sent_at = Column(DateTime, nullable=False)
    channel = Column(String, nullable=False, default="email")
    status = Column(String, nullable=False)
    error = Column(Text)
    link = Column(String)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('sent','failed','skipped')"),
    )
    invoice = relationship("Invoice", back_populates="reminders")
