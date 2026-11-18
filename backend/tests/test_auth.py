import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, get_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def test_register_login_me(auth_helper):
    """Test successful registration, login, and get user info"""
    register, login, get_me = auth_helper
    
    # Use unique email for test
    email = f"test_user_{pytest.__version__}@example.com"
    password = "testpassword123"
    
    # Register new user
    response = register(email, password)
    assert response.status_code == 201
    assert "access_token" in response.json()
    
    # Login with same credentials
    response = login(email, password)
    assert response.status_code == 200
    assert "access_token" in response.json()
    
    # Get current user info
    response = get_me()
    assert response.status_code == 200
    user_data = response.json()
    assert user_data["email"] == email
    assert "id" in user_data
    assert "created_at" in user_data

def test_duplicate_register(auth_helper, client):
    """Test duplicate registration returns 400"""
    register, _, _ = auth_helper
    
    email = "duplicate@example.com"
    password = "testpassword123"
    
    # First registration should succeed
    response = register(email, password)
    assert response.status_code == 201
    
    # Second registration should fail with 400
    response = register(email, password)
    # Register endpoint returns 400 for duplicate email
    assert response.status_code == 400

def test_invalid_login(auth_helper, client):
    """Test login with invalid credentials returns 401"""
    register, _, _ = auth_helper
    
    email = "test_user2@example.com"
    password = "testpassword123"
    
    # Register user first
    response = register(email, password)
    assert response.status_code == 201
    
    # Try login with wrong password
    response = client.post("/api/auth/login", json={
        "email": email,
        "password": "wrongpassword"
    })
    assert response.status_code == 401
    assert "Invalid credentials" in response.text
    
    # Try login with wrong email
    response = client.post("/api/auth/login", json={
        "email": "nonexistent@example.com",
        "password": password
    })
    assert response.status_code == 401
    assert "Invalid credentials" in response.text

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
