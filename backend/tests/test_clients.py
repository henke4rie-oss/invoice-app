import pytest


# Helper to get unique user for tests
def get_unique_test_user(auth_helper):
    """Get a test user with unique credentials"""
    import uuid
    email = f"test_user_{uuid.uuid4()}@example.com"
    password = "testpassword123"
    
    register, login, _ = auth_helper
    
    # Register user
    register_response = register(email, password)
    assert register_response.status_code == 201
    
    # Login to get token
    login_response = login(email, password)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    return email, password, token

# Test CRUD for clients
def test_create_client(auth_helper, client, get_headers):
    """Test creating a new client"""
    email, password, token = get_unique_test_user(auth_helper)
    
    # Create a client
    client_data = {
        "name": "Acme Corp",
        "email": "contact@acme.com",
        "company": "Acme Corporation",
        "notes": "Important client"
    }
    
    response = client.post("/api/clients", json=client_data, headers=get_headers(token))
    assert response.status_code == 201
    
    client_data = response.json()
    assert client_data["name"] == "Acme Corp"
    assert client_data["email"] == "contact@acme.com"
    assert client_data["company"] == "Acme Corporation"
    assert client_data["notes"] == "Important client"
    assert "id" in client_data
    assert "user_id" in client_data
    assert "created_at" in client_data
    assert "updated_at" in client_data

def test_list_clients(auth_helper, client, get_headers):
    """Test listing clients"""
    email, password, token = get_unique_test_user(auth_helper)
    
    # Create multiple clients
    clients_data = [
        {"name": "Client A", "email": "a@example.com"},
        {"name": "Client B", "email": "b@example.com"},
        {"name": "Client C", "email": "c@example.com"},
    ]
    
    for client_data in clients_data:
        response = client.post("/api/clients", json=client_data, headers=get_headers(token))
        assert response.status_code == 201
    
    # List clients
    response = client.get("/api/clients", headers=get_headers(token))
    assert response.status_code == 200
    
    clients = response.json()
    assert len(clients) == 3
    
    # Check client data
    client_names = [c["name"] for c in clients]
    assert "Client A" in client_names
    assert "Client B" in client_names
    assert "Client C" in client_names

def test_get_client(auth_helper, client, get_headers):
    """Test getting a specific client"""
    email, password, token = get_unique_test_user(auth_helper)
    
    # Create a client
    client_data = {"name": "Test Client", "email": "test@example.com"}
    response = client.post("/api/clients", json=client_data, headers=get_headers(token))
    assert response.status_code == 201
    client_id = response.json()["id"]
    
    # Get the client
    response = client.get(f"/api/clients/{client_id}", headers=get_headers(token))
    assert response.status_code == 200
    
    client_data = response.json()
    assert client_data["id"] == client_id
    assert client_data["name"] == "Test Client"
    assert client_data["email"] == "test@example.com"

def test_update_client(auth_helper, client, get_headers):
    """Test updating a client"""
    email, password, token = get_unique_test_user(auth_helper)
    
    # Create a client
    client_data = {"name": "Original Client", "email": "original@example.com"}
    response = client.post("/api/clients", json=client_data, headers=get_headers(token))
    assert response.status_code == 201
    client_id = response.json()["id"]
    
    # Update the client
    update_data = {
        "name": "Updated Client",
        "email": "updated@example.com",
        "company": "New Company",
        "notes": "Updated notes"
    }
    
    response = client.put(f"/api/clients/{client_id}", json=update_data, headers=get_headers(token))
    assert response.status_code == 200
    
    updated_client = response.json()
    assert updated_client["id"] == client_id
    assert updated_client["name"] == "Updated Client"
    assert updated_client["email"] == "updated@example.com"
    assert updated_client["company"] == "New Company"
    assert updated_client["notes"] == "Updated notes"
    
    # Verify update by getting the client
    response = client.get(f"/api/clients/{client_id}", headers=get_headers(token))
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Client"

def test_delete_client(auth_helper, client, get_headers):
    """Test deleting a client"""
    email, password, token = get_unique_test_user(auth_helper)
    
    # Create a client
    client_data = {"name": "Client to Delete", "email": "delete@example.com"}
    response = client.post("/api/clients", json=client_data, headers=get_headers(token))
    assert response.status_code == 201
    client_id = response.json()["id"]
    
    # Delete the client
    response = client.delete(f"/api/clients/{client_id}", headers=get_headers(token))
    assert response.status_code == 204
    
    # Verify client is deleted
    response = client.get(f"/api/clients/{client_id}", headers=get_headers(token))
    assert response.status_code == 404

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
