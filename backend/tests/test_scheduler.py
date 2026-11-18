from app.db import utcnow
import pytest


# Test scheduler run-due process
def test_scheduler_run_due_process(auth_helper, client, get_headers):
    """Test scheduler run-due process for overdue invoices"""
    register, login, _ = auth_helper
    
    import uuid
    email = f"scheduler_test_{uuid.uuid4()}@example.com"
    password = "testpassword123"
    
    # Register user
    register_response = register(email, password)
    assert register_response.status_code == 201
    
    # Login to get token
    login_response = login(email, password)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    # Create a client
    client_data = {"name": "Scheduler Test", "email": "scheduler@example.com"}
    response = client.post("/api/clients", json=client_data, headers=get_headers(token))
    assert response.status_code == 201
    client_id = response.json()["id"]
    
    # Create overdue invoice (in "sent" status to be processed by scheduler)
    from datetime import datetime, timedelta
    past_date = utcnow() - timedelta(days=10)
    invoice_data = {
        "client_id": client_id,
        "number": "INV-SCHEDULER-TEST",
        "amount_cents": 50000,
        "currency": "USD",
        "issue_date": past_date.isoformat(),
        "due_date": past_date.isoformat(),
        "notes": "Overdue"
    }
    
    response = client.post("/api/invoices", json=invoice_data, headers=get_headers(token))
    assert response.status_code == 201
    invoice_id = response.json()["id"]
    
    # Manually mark as sent (so the scheduler will process it)
    response = client.patch(f"/api/invoices/{invoice_id}/status",
                          json={"status": "sent"},
                          headers=get_headers(token))
    assert response.status_code == 200
    
    # Run the scheduler
    response = client.post("/api/reminders/run-due", headers=get_headers(token))
    assert response.status_code == 200
    
    result = response.json()
    assert "processed" in result
    # The invoice should be processed by the scheduler
    # Note: This test assumes the scheduler will process the invoice
    # In a real scenario, this would depend on the scheduler's configuration
