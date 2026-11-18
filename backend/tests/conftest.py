import os
import re
import tempfile
from pathlib import Path

# Must be set before the app is imported: tests never touch the dev database or start the scheduler.
# Start Postgres with `docker compose up -d db`; the test database ("invoice_test") is created on demand.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://invoice:invoice@localhost:5433/invoice_test")
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["LOGOS_DIR"] = tempfile.mkdtemp(prefix="invoice-test-logos-")  # never touch the real data/logos
os.environ["DEMO_ENABLED"] = "false"  # demo tests switch it on explicitly; other tests skip the seeding cost

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import settings
from app.db import engine, get_db
from app.main import app

BACKEND_DIR = Path(__file__).resolve().parent.parent


def alembic_config() -> Config:
    return Config(str(BACKEND_DIR / "alembic.ini"))


def _ensure_database_exists(url) -> None:
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            if not conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database}).scalar():
                conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def _database():
    """Fresh schema built by the real Alembic migrations (so they are exercised on every run)."""
    url = make_url(settings.database_url)
    # Safety: this fixture wipes the schema, so it must never be pointed at a real database.
    if not re.fullmatch(r"[A-Za-z0-9_]+_test", url.database or ""):
        pytest.exit(f"Refusing to run tests against database {url.database!r}: its name must end with '_test'", returncode=2)
    _ensure_database_exists(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    command.upgrade(alembic_config(), "head")
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def db_connection(_database):
    """Every test runs inside one transaction that is rolled back afterwards.

    The API's sessions join it with savepoints, so the app's own commit()/rollback() calls work
    normally but nothing survives the test.
    """
    connection = engine.connect()
    transaction = connection.begin()

    def override_get_db():
        session = Session(bind=connection, autoflush=False, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield connection
    app.dependency_overrides.pop(get_db, None)
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_connection):
    """Test client whose sessions run inside the per-test transaction."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session(client):
    """A session on the same transaction the API uses (via the app's get_db override)."""
    gen = app.dependency_overrides[get_db]()
    db = next(gen)
    yield db
    gen.close()


# Auth helper fixture that returns response functions
@pytest.fixture
def auth_helper(client):
    """Helper for auth operations"""
    current_token = None
    
    def _register(email, password):
        nonlocal current_token
        response = client.post("/api/auth/register", json={"email": email, "password": password})
        if response.status_code == 201:
            result = response.json()
            current_token = result.get("access_token")
        return response
    
    def _login(email, password):
        nonlocal current_token
        response = client.post("/api/auth/login", json={"email": email, "password": password})
        if response.status_code == 200:
            result = response.json()
            current_token = result.get("access_token")
        return response
    
    def _get_me():
        nonlocal current_token
        if current_token:
            response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {current_token}"})
        else:
            response = client.get("/api/auth/me")
        return response
    
    return _register, _login, _get_me


@pytest.fixture
def create_user(client):
    import uuid
    
    def _create_user(email=None, password=None):
        if email is None:
            email = f"test_{uuid.uuid4()}@example.com"
        if password is None:
            password = "testpassword123"
        
        response = client.post("/api/auth/register", json={"email": email, "password": password})
        
        login_response = client.post("/api/auth/login", json={"email": email, "password": password})
        
        return email, password, login_response.json()["access_token"]
    
    return _create_user

# Helper to create test headers
@pytest.fixture
def get_headers():
    def _get_headers(token):
        return {"Authorization": f"Bearer {token}"}
    return _get_headers
