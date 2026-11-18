"""Database layer: URL handling, migrations stay in sync with the models, Postgres enforces the rules."""
from datetime import timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import delete, inspect, text
from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.db import Base, engine, utcnow
from app.models import Client, Invoice, Reminder, User


def _alembic_config() -> Config:
    return Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))


# ---------- URL handling ----------

@pytest.mark.parametrize("given, expected", [
    ("postgres://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
    ("postgresql://u:p@host/db?sslmode=require", "postgresql+psycopg://u:p@host/db?sslmode=require"),
    ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
])
def test_hosted_database_urls_use_the_psycopg_driver(given, expected):
    assert Settings(database_url=given).database_url == expected


# ---------- migrations ----------

def test_migrations_match_the_models():
    """If this fails, a model changed without a migration: run `alembic revision --autogenerate`."""
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, Base.metadata) == []


def test_migrations_roundtrip_down_and_up():
    config = _alembic_config()
    try:
        command.downgrade(config, "base")
        assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    finally:
        command.upgrade(config, "head")  # always leave the schema in place for the other tests
    assert {"users", "clients", "invoices", "reminders"} <= set(inspect(engine).get_table_names())


def test_foreign_keys_are_indexed():
    inspector = inspect(engine)
    assert "ix_clients_user_id" in {i["name"] for i in inspector.get_indexes("clients")}
    assert "ix_invoices_client_id" in {i["name"] for i in inspector.get_indexes("invoices")}
    assert "ix_reminders_invoice_id" in {i["name"] for i in inspector.get_indexes("reminders")}


# ---------- constraints Postgres enforces ----------

def _user(db, email="db@example.com"):
    user = User(email=email, password_hash="x")
    db.add(user)
    db.flush()
    return user


def _client(db, user):
    client = Client(user_id=user.id, name="C")
    db.add(client)
    db.flush()
    return client


def _invoice(db, user, client, number="INV-1", status="draft"):
    now = utcnow()
    invoice = Invoice(user_id=user.id, client_id=client.id, number=number, amount_cents=100, currency="ZAR",
                      issue_date=now, due_date=now + timedelta(days=30), status=status)
    db.add(invoice)
    db.flush()
    return invoice


def test_invalid_invoice_status_is_rejected(db_session):
    user = _user(db_session)
    client = _client(db_session, user)
    with pytest.raises(IntegrityError):
        _invoice(db_session, user, client, status="bogus")
    db_session.rollback()


def test_invoice_numbers_are_unique_per_user_but_not_across_users(db_session):
    a, b = _user(db_session, "a@example.com"), _user(db_session, "b@example.com")
    client_a, client_b = _client(db_session, a), _client(db_session, b)
    _invoice(db_session, a, client_a, "INV-1")
    _invoice(db_session, b, client_b, "INV-1")  # same number, different user: fine
    with pytest.raises(IntegrityError):
        _invoice(db_session, a, client_a, "INV-1")
    db_session.rollback()


def test_a_client_with_invoices_cannot_be_deleted(db_session):
    user = _user(db_session)
    client = _client(db_session, user)
    _invoice(db_session, user, client)
    with pytest.raises(IntegrityError):
        db_session.execute(delete(Client).where(Client.id == client.id))
    db_session.rollback()


def test_deleting_a_user_cascades_to_everything_they_own(db_session):
    user = _user(db_session)
    client = _client(db_session, user)
    invoice = _invoice(db_session, user, client)
    db_session.add(Reminder(invoice_id=invoice.id, sent_at=utcnow(), channel="email", status="sent"))
    db_session.flush()

    db_session.execute(delete(User).where(User.id == user.id))
    db_session.flush()
    for table in ("clients", "invoices", "reminders"):
        assert db_session.execute(text(f"SELECT count(*) FROM {table}")).scalar() == 0


def test_email_is_unique(db_session):
    _user(db_session, "dup@example.com")
    with pytest.raises(IntegrityError):
        _user(db_session, "dup@example.com")
    db_session.rollback()


# ---------- production guard ----------

def test_production_refuses_to_start_on_the_development_database(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setattr("app.main.settings.debug", False)
    monkeypatch.setattr("app.main.settings.secret_key", "x" * 40)
    monkeypatch.setattr("app.main.settings.database_url", "postgresql+psycopg://invoice:invoice@localhost:5433/invoice")
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        with TestClient(app):
            pass
