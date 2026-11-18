import os
import tempfile

# Must be set before the app is imported: tests never touch the real dev database or start the scheduler
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["LOGOS_DIR"] = tempfile.mkdtemp(prefix="invoice-test-logos-")  # never touch the real data/logos
os.environ["DEMO_ENABLED"] = "false"  # demo tests switch it on explicitly; other tests skip the seeding cost

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, get_db

# Check if SQLAlchemy is available
try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False
    print("Warning: SQLAlchemy not available, tests may fail")

# In-memory SQLite database with StaticPool for shared connection
if SQLALCHEMY_AVAILABLE:
    TEST_ENGINE = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False
    )
    
    # Enable foreign keys for SQLite
    if SQLALCHEMY_AVAILABLE:
        from sqlalchemy import event
        @event.listens_for(TEST_ENGINE, "connect")
        def _enable_foreign_keys(dbapi_conn, connection_record):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        TESTING_SESSION_LOCAL = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=TEST_ENGINE
        )

# Function to get test database session
def get_test_db():
    """Generator function to yield a test database session"""
    if not SQLALCHEMY_AVAILABLE:
        yield None
        return
    
    db = TESTING_SESSION_LOCAL()
    try:
        yield db
    finally:
        db.close()

# Create all tables in test database before any tests run
@pytest.fixture(autouse=True)
def create_tables():
    """Create all tables in test database before tests run"""
    if SQLALCHEMY_AVAILABLE:
        Base.metadata.create_all(bind=TEST_ENGINE)
        yield
        Base.metadata.drop_all(bind=TEST_ENGINE)
    else:
        yield

# Test client fixture that uses the test database
@pytest.fixture
def client():
    """Test client fixture with test database"""
    # Override get_db dependency with test database
    original_get_db = get_db
    app.dependency_overrides[get_db] = get_test_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    del app.dependency_overrides[get_db]


@pytest.fixture
def db_session(client):
    """A session on the same test database the API uses (via the app's get_db override)."""
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
        
        if SQLALCHEMY_AVAILABLE:
            from app.db import Base
            Base.metadata.create_all(bind=TEST_ENGINE)
        
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
