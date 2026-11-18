import pytest


# Helper to create test user and client
def create_test_user_and_client(auth_helper, client, get_headers):
    """Helper to create a test user and client"""
    register, login, _ = auth_helper
    
    import uuid
    email = f"reminder_test_{uuid.uuid4()}@example.com"
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
    
    return email, password, token, client_id

# Test sending reminder
def test_send_reminder(auth_helper, client, get_headers):
    """Test sending a reminder"""
    email, password, token, client_id = create_test_user_and_client(auth_helper, client, get_headers)
    
    # Create an invoice
    invoice_data = {
        "client_id": client_id,
        "number": "INV-REMINDER-TEST",
        "amount_cents": 50000,
        "currency": "USD",
        "issue_date": "2026-01-01T00:00:00",
        "due_date": "2026-02-01T00:00:00",
    }
    
    response = client.post("/api/invoices", json=invoice_data, headers=get_headers(token))
    assert response.status_code == 201
    invoice_id = response.json()["id"]
    
    # Send reminder (empty JSON body since channel is optional with default)
    response = client.post(f"/api/invoices/{invoice_id}/reminders", json={}, headers=get_headers(token))
    assert response.status_code == 201
    
    reminder_data = response.json()
    assert reminder_data["invoice_id"] == invoice_id
    assert reminder_data["channel"] == "email"
    assert reminder_data["status"] == "sent"
    assert "id" in reminder_data

# Test reminder deduplication
def test_reminder_deduplication(auth_helper, client, get_headers):
    """Test that reminders are skipped if already sent today"""
    email, password, token, client_id = create_test_user_and_client(auth_helper, client, get_headers)
    
    # Create an invoice
    invoice_data = {
        "client_id": client_id,
        "number": "INV-DEDUP-TEST",
        "amount_cents": 60000,
        "currency": "USD",
        "issue_date": "2026-01-01T00:00:00",
        "due_date": "2026-02-01T00:00:00",
    }
    
    response = client.post("/api/invoices", json=invoice_data, headers=get_headers(token))
    assert response.status_code == 201
    invoice_id = response.json()["id"]
    
    # Send first reminder
    response = client.post(f"/api/invoices/{invoice_id}/reminders", json={}, headers=get_headers(token))
    assert response.status_code == 201
    
    first_reminder = response.json()
    assert first_reminder["status"] == "sent"
    
    # Send second reminder (should be skipped)
    response = client.post(f"/api/invoices/{invoice_id}/reminders", json={}, headers=get_headers(token))
    assert response.status_code == 201
    
    second_reminder = response.json()
    assert second_reminder["invoice_id"] == invoice_id
    assert second_reminder["status"] == "skipped"
    assert "Duplicate today" in second_reminder.get("error", "")

# Test reminder for paid invoice (should fail)
def test_reminder_for_paid_invoice(auth_helper, client, get_headers):
    """Test sending reminder for paid invoice returns 409"""
    email, password, token, client_id = create_test_user_and_client(auth_helper, client, get_headers)
    
    # Create and pay an invoice (need to go through sent status first)
    invoice_data = {
        "client_id": client_id,
        "number": "INV-PAID-TEST",
        "amount_cents": 70000,
        "currency": "USD",
        "issue_date": "2026-01-01T00:00:00",
        "due_date": "2026-02-01T00:00:00",
    }
    
    response = client.post("/api/invoices", json=invoice_data, headers=get_headers(token))
    assert response.status_code == 201
    invoice_id = response.json()["id"]
    
    # First transition to sent status
    response = client.patch(f"/api/invoices/{invoice_id}/status",
                          json={"status": "sent"},
                          headers=get_headers(token))
    assert response.status_code == 200
    
    # Then transition to paid status
    response = client.patch(f"/api/invoices/{invoice_id}/status",
                          json={"status": "paid"},
                          headers=get_headers(token))
    assert response.status_code == 200
    
    # Try to send reminder (should fail)
    response = client.post(f"/api/invoices/{invoice_id}/reminders", json={}, headers=get_headers(token))
    assert response.status_code == 409
    assert "paid" in response.text.lower()

# Test listing reminders
def test_list_reminders(auth_helper, client, get_headers):
    """Test listing reminders"""
    email, password, token, client_id = create_test_user_and_client(auth_helper, client, get_headers)
    
    # Create an invoice
    invoice_data = {
        "client_id": client_id,
        "number": "INV-LIST-TEST",
        "amount_cents": 80000,
        "currency": "USD",
        "issue_date": "2026-01-01T00:00:00",
        "due_date": "2026-02-01T00:00:00",
    }
    
    response = client.post("/api/invoices", json=invoice_data, headers=get_headers(token))
    assert response.status_code == 201
    invoice_id = response.json()["id"]
    
    # Send a reminder
    response = client.post(f"/api/invoices/{invoice_id}/reminders", json={}, headers=get_headers(token))
    assert response.status_code == 201
    
    # List reminders
    response = client.get(f"/api/invoices/{invoice_id}/reminders", headers=get_headers(token))
    assert response.status_code == 200
    
    reminders = response.json()
    assert len(reminders) == 1
    assert reminders[0]["invoice_id"] == invoice_id
    assert reminders[0]["channel"] == "email"


# Regression: reminders on overdue invoices used to fail (overdue -> sent is not a valid transition)
def test_reminder_for_overdue_invoice(auth_helper, client, get_headers):
    """Sending a reminder for an overdue invoice succeeds and leaves it overdue"""
    email, password, token, client_id = create_test_user_and_client(auth_helper, client, get_headers)
    headers = get_headers(token)

    invoice_data = {
        "client_id": client_id,
        "number": "INV-OVERDUE-TEST",
        "amount_cents": 90000,
        "currency": "USD",
        "issue_date": "2026-01-01T00:00:00",
        "due_date": "2026-02-01T00:00:00",
    }
    response = client.post("/api/invoices", json=invoice_data, headers=headers)
    assert response.status_code == 201
    invoice_id = response.json()["id"]

    for new_status in ("sent", "overdue"):
        response = client.patch(f"/api/invoices/{invoice_id}/status", json={"status": new_status}, headers=headers)
        assert response.status_code == 200

    response = client.post(f"/api/invoices/{invoice_id}/reminders", json={}, headers=headers)
    assert response.status_code == 201
    assert response.json()["status"] == "sent"

    response = client.get(f"/api/invoices/{invoice_id}", headers=headers)
    assert response.json()["status"] == "overdue"
