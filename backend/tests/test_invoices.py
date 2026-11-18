from app.db import utcnow
from datetime import timedelta
import pytest


# Test invoice creation
def test_create_invoice(auth_helper, client, get_headers):
    """Test creating a new invoice"""
    register, login, _ = auth_helper
    
    import uuid
    email = f"invoice_test_{uuid.uuid4()}@example.com"
    password = "testpassword123"
    
    # Register user
    register_response = register(email, password)
    assert register_response.status_code == 201
    
    # Login to get token
    login_response = login(email, password)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    # Create a client
    client_data = {"name": "Test Client", "email": "client@example.com"}
    response = client.post("/api/clients", json=client_data, headers=get_headers(token))
    assert response.status_code == 201
    client_id = response.json()["id"]
    
    # Create an invoice
    from datetime import datetime, timedelta
    invoice_data = {
        "client_id": client_id,
        "number": "INV-001",
        "amount_cents": 50000,
        "currency": "USD",
        "issue_date": utcnow().isoformat(),
        "due_date": (utcnow() + timedelta(days=30)).isoformat(),
        "notes": "First invoice"
    }
    
    response = client.post("/api/invoices", json=invoice_data, headers=get_headers(token))
    assert response.status_code == 201
    
    invoice_data = response.json()
    assert invoice_data["number"] == "INV-001"
    assert invoice_data["amount_cents"] == 50000
    assert invoice_data["currency"] == "USD"
    assert invoice_data["status"] == "draft"
    assert invoice_data["client_name"] == "Test Client"
    assert "id" in invoice_data
    assert "user_id" in invoice_data
    assert "created_at" in invoice_data
    assert "updated_at" in invoice_data

# Test listing invoices with filters
def test_list_invoices(auth_helper, client, get_headers):
    """Test listing invoices with filters"""
    register, login, _ = auth_helper
    
    import uuid
    email = f"invoice_test_{uuid.uuid4()}@example.com"
    password = "testpassword123"
    
    # Register user
    register_response = register(email, password)
    assert register_response.status_code == 201
    
    # Login to get token
    login_response = login(email, password)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    # Create a client
    client_data = {"name": "Test Client", "email": "client@example.com"}
    response = client.post("/api/clients", json=client_data, headers=get_headers(token))
    assert response.status_code == 201
    client_id = response.json()["id"]
    
    from datetime import datetime, timedelta
    # Create multiple invoices
    invoice_data1 = {
        "client_id": client_id,
        "number": "INV-001",
        "amount_cents": 50000,
        "currency": "USD",
        "issue_date": utcnow().isoformat(),
        "due_date": (utcnow() + timedelta(days=30)).isoformat(),
    }
    
    invoice_data2 = {
        "client_id": client_id,
        "number": "INV-002",
        "amount_cents": 75000,
        "currency": "USD",
        "issue_date": utcnow().isoformat(),
        "due_date": (utcnow() + timedelta(days=60)).isoformat(),
    }
    
    response1 = client.post("/api/invoices", json=invoice_data1, headers=get_headers(token))
    assert response1.status_code == 201
    invoice1 = response1.json()
    
    response2 = client.post("/api/invoices", json=invoice_data2, headers=get_headers(token))
    assert response2.status_code == 201
    invoice2 = response2.json()
    
    # List all invoices
    response = client.get("/api/invoices", headers=get_headers(token))
    assert response.status_code == 200
    invoices = response.json()
    assert len(invoices) == 2
    
    # Test filtering by status
    response = client.get("/api/invoices?status=draft", headers=get_headers(token))
    assert response.status_code == 200
    invoices = response.json()
    assert len(invoices) == 2  # Both are draft
    
    # Test filtering by client_id
    response = client.get(f"/api/invoices?client_id={client_id}", headers=get_headers(token))
    assert response.status_code == 200
    invoices = response.json()
    assert len(invoices) == 2

# Test getting a specific invoice
def test_get_invoice(auth_helper, client, get_headers):
    """Test getting a specific invoice"""
    register, login, _ = auth_helper
    
    import uuid
    email = f"invoice_test_{uuid.uuid4()}@example.com"
    password = "testpassword123"
    
    # Register user
    register_response = register(email, password)
    assert register_response.status_code == 201
    
    # Login to get token
    login_response = login(email, password)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    # Create a client
    client_data = {"name": "Test Client", "email": "client@example.com"}
    response = client.post("/api/clients", json=client_data, headers=get_headers(token))
    assert response.status_code == 201
    client_id = response.json()["id"]
    
    from datetime import datetime, timedelta
    # Create an invoice
    invoice_data = {
        "client_id": client_id,
        "number": "INV-GET-TEST",
        "amount_cents": 25000,
        "currency": "USD",
        "issue_date": utcnow().isoformat(),
        "due_date": (utcnow() + timedelta(days=45)).isoformat(),
    }
    
    response = client.post("/api/invoices", json=invoice_data, headers=get_headers(token))
    assert response.status_code == 201
    invoice_id = response.json()["id"]
    
    # Get the invoice
    response = client.get(f"/api/invoices/{invoice_id}", headers=get_headers(token))
    assert response.status_code == 200
    
    invoice = response.json()
    assert invoice["id"] == invoice_id
    assert invoice["number"] == "INV-GET-TEST"
    assert invoice["amount_cents"] == 25000

# Test status transitions
def test_status_transitions(auth_helper, client, get_headers):
    """Test invoice status transitions"""
    register, login, _ = auth_helper
    
    import uuid
    email = f"invoice_test_{uuid.uuid4()}@example.com"
    password = "testpassword123"
    
    # Register user
    register_response = register(email, password)
    assert register_response.status_code == 201
    
    # Login to get token
    login_response = login(email, password)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    # Create a client
    client_data = {"name": "Test Client", "email": "client@example.com"}
    response = client.post("/api/clients", json=client_data, headers=get_headers(token))
    assert response.status_code == 201
    client_id = response.json()["id"]
    
    from datetime import datetime, timedelta
    # Create an invoice
    invoice_data = {
        "client_id": client_id,
        "number": "INV-STATUS-TEST",
        "amount_cents": 30000,
        "currency": "USD",
        "issue_date": utcnow().isoformat(),
        "due_date": (utcnow() + timedelta(days=30)).isoformat(),
    }
    
    response = client.post("/api/invoices", json=invoice_data, headers=get_headers(token))
    assert response.status_code == 201
    invoice_id = response.json()["id"]
    
    # Transition from draft to sent
    response = client.patch(f"/api/invoices/{invoice_id}/status", 
                          json={"status": "sent"},
                          headers=get_headers(token))
    assert response.status_code == 200
    
    updated_invoice = response.json()
    assert updated_invoice["status"] == "sent"
    
    # Transition from sent to paid
    response = client.patch(f"/api/invoices/{invoice_id}/status",
                          json={"status": "paid"},
                          headers=get_headers(token))
    assert response.status_code == 200
    
    updated_invoice = response.json()
    assert updated_invoice["status"] == "paid"

# Test duplicate invoice number
def test_duplicate_invoice_number(auth_helper, client, get_headers):
    """Test duplicate invoice number returns 409"""
    register, login, _ = auth_helper
    
    import uuid
    email = f"invoice_test_{uuid.uuid4()}@example.com"
    password = "testpassword123"
    
    # Register user
    register_response = register(email, password)
    assert register_response.status_code == 201
    
    # Login to get token
    login_response = login(email, password)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    # Create a client
    client_data = {"name": "Test Client", "email": "client@example.com"}
    response = client.post("/api/clients", json=client_data, headers=get_headers(token))
    assert response.status_code == 201
    client_id = response.json()["id"]
    
    from datetime import datetime, timedelta
    # Create first invoice
    invoice_data = {
        "client_id": client_id,
        "number": "INV-DUP-TEST",
        "amount_cents": 40000,
        "currency": "USD",
        "issue_date": utcnow().isoformat(),
        "due_date": (utcnow() + timedelta(days=30)).isoformat(),
    }
    
    response = client.post("/api/invoices", json=invoice_data, headers=get_headers(token))
    assert response.status_code == 201
    
    # Try to create duplicate invoice
    response = client.post("/api/invoices", json=invoice_data, headers=get_headers(token))
    assert response.status_code == 409
    assert "Duplicate invoice number" in response.text

# Test deleting an invoice
def test_delete_invoice(auth_helper, client, get_headers):
    """Test deleting an invoice"""
    register, login, _ = auth_helper
    
    import uuid
    email = f"invoice_test_{uuid.uuid4()}@example.com"
    password = "testpassword123"
    
    # Register user
    register_response = register(email, password)
    assert register_response.status_code == 201
    
    # Login to get token
    login_response = login(email, password)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    # Create a client
    client_data = {"name": "Test Client", "email": "client@example.com"}
    response = client.post("/api/clients", json=client_data, headers=get_headers(token))
    assert response.status_code == 201
    client_id = response.json()["id"]
    
    from datetime import datetime, timedelta
    # Create an invoice
    invoice_data = {
        "client_id": client_id,
        "number": "INV-DELETE-TEST",
        "amount_cents": 35000,
        "currency": "USD",
        "issue_date": utcnow().isoformat(),
        "due_date": (utcnow() + timedelta(days=30)).isoformat(),
    }
    
    response = client.post("/api/invoices", json=invoice_data, headers=get_headers(token))
    assert response.status_code == 201
    invoice_id = response.json()["id"]
    
    # Delete the invoice
    response = client.delete(f"/api/invoices/{invoice_id}", headers=get_headers(token))
    assert response.status_code == 204
    
    # Verify invoice is deleted
    response = client.get(f"/api/invoices/{invoice_id}", headers=get_headers(token))
    assert response.status_code == 404

# Test marking invoice overdue
def test_mark_invoice_overdue(auth_helper, client, get_headers):
    """Test marking invoice as overdue"""
    register, login, _ = auth_helper
    
    import uuid
    email = f"invoice_test_{uuid.uuid4()}@example.com"
    password = "testpassword123"
    
    # Register user
    register_response = register(email, password)
    assert register_response.status_code == 201
    
    # Login to get token
    login_response = login(email, password)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    # Create a client
    client_data = {"name": "Test Client", "email": "client@example.com"}
    response = client.post("/api/clients", json=client_data, headers=get_headers(token))
    assert response.status_code == 201
    client_id = response.json()["id"]
    
    from datetime import datetime, timedelta
    # Create an invoice with past due date
    past_date = utcnow() - timedelta(days=10)
    invoice_data = {
        "client_id": client_id,
        "number": "INV-OVERDUE-TEST",
        "amount_cents": 60000,
        "currency": "USD",
        "issue_date": past_date.isoformat(),
        "due_date": past_date.isoformat(),
    }
    
    response = client.post("/api/invoices", json=invoice_data, headers=get_headers(token))
    assert response.status_code == 201
    invoice_id = response.json()["id"]
    
    # Mark as overdue
    response = client.get(f"/api/invoices/{invoice_id}/mark-overdue", headers=get_headers(token))
    assert response.status_code == 200
    
    invoice = response.json()
    assert invoice["status"] == "overdue"


# Regression: PUT /api/invoices/{id} used to recurse into itself (name shadowing) and return 500
def test_update_invoice_put(client, create_user, get_headers):
    """PUT updates invoice fields"""
    _, _, token = create_user()
    headers = get_headers(token)
    client_id = client.post("/api/clients", json={"name": "Put Client"}, headers=headers).json()["id"]
    invoice = client.post("/api/invoices", json={
        "client_id": client_id,
        "number": "INV-PUT-1",
        "amount_cents": 10000,
        "currency": "USD",
        "issue_date": utcnow().isoformat(),
        "due_date": (utcnow() + timedelta(days=30)).isoformat(),
    }, headers=headers).json()

    response = client.put(f"/api/invoices/{invoice['id']}", json={"amount_cents": 12345, "notes": "updated"}, headers=headers)
    assert response.status_code == 200
    assert response.json()["amount_cents"] == 12345
    assert response.json()["notes"] == "updated"

    assert client.put("/api/invoices/99999", json={"notes": "x"}, headers=headers).status_code == 404


def test_draft_invoice_can_be_marked_paid(client, create_user, get_headers):
    """A payment can arrive before the invoice was ever sent: draft -> paid is allowed"""
    _, _, token = create_user()
    headers = get_headers(token)
    client_id = client.post("/api/clients", json={"name": "Quick Payer"}, headers=headers).json()["id"]
    invoice = client.post("/api/invoices", json={
        "client_id": client_id,
        "number": "INV-QUICKPAY",
        "amount_cents": 5000,
        "currency": "usd",  # lowercase is normalised
        "issue_date": "2026-03-01",
        "due_date": "2026-04-01",
    }, headers=headers)
    assert invoice.status_code == 201
    assert invoice.json()["currency"] == "USD"

    response = client.patch(f"/api/invoices/{invoice.json()['id']}/status", json={"status": "paid"}, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "paid"
