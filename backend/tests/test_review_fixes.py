"""Regression tests for the Phase 4 review findings."""


def _invoice(client_id, number="R-1", **extra):
    body = {
        "client_id": client_id,
        "number": number,
        "amount_cents": 10000,
        "currency": "USD",
        "issue_date": "2026-01-01",
        "due_date": "2026-02-01",
    }
    body.update(extra)
    return body


def _setup(client, create_user, get_headers, phone=None):
    _, _, token = create_user()
    headers = get_headers(token)
    payload = {"name": "Owner Client", "email": "c@example.com"}
    if phone:
        payload["phone"] = phone
    client_id = client.post("/api/clients", json=payload, headers=headers).json()["id"]
    return headers, client_id


# 1. Cross-tenant access
def test_cannot_invoice_another_users_client(client, create_user, get_headers):
    a_headers, a_client = _setup(client, create_user, get_headers)
    b_headers, b_client = _setup(client, create_user, get_headers)

    r = client.post("/api/invoices", json=_invoice(a_client), headers=b_headers)
    assert r.status_code == 404
    assert "Victim" not in r.text and "Owner Client" not in r.text

    own = client.post("/api/invoices", json=_invoice(b_client, "R-OWN"), headers=b_headers).json()["id"]
    r = client.put(f"/api/invoices/{own}", json={"client_id": a_client}, headers=b_headers)
    assert r.status_code == 404

    # Still points at B's own client
    assert client.get(f"/api/invoices/{own}", headers=b_headers).json()["client_id"] == b_client


# 2. PUT status handling
def test_put_status_validation_and_transitions(client, create_user, get_headers):
    headers, client_id = _setup(client, create_user, get_headers)
    inv = client.post("/api/invoices", json=_invoice(client_id), headers=headers).json()["id"]

    assert client.put(f"/api/invoices/{inv}", json={"status": "bogus"}, headers=headers).status_code == 422

    r = client.put(f"/api/invoices/{inv}", json={"status": "overdue", "notes": "late"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "overdue" and r.json()["notes"] == "late"

    client.put(f"/api/invoices/{inv}", json={"status": "paid"}, headers=headers)
    # paid is final: no way back, and the rejected request must not write other fields
    r = client.put(f"/api/invoices/{inv}", json={"status": "draft", "notes": "should not stick"}, headers=headers)
    assert r.status_code == 409
    after = client.get(f"/api/invoices/{inv}", headers=headers).json()
    assert after["status"] == "paid" and after["notes"] == "late"


def test_put_duplicate_number_is_409(client, create_user, get_headers):
    headers, client_id = _setup(client, create_user, get_headers)
    client.post("/api/invoices", json=_invoice(client_id, "DUP-1"), headers=headers)
    second = client.post("/api/invoices", json=_invoice(client_id, "DUP-2"), headers=headers).json()["id"]
    assert client.put(f"/api/invoices/{second}", json={"number": "DUP-1"}, headers=headers).status_code == 409
    # session is still usable after the rollback
    assert client.get(f"/api/invoices/{second}", headers=headers).status_code == 200


# 3. Dedup is per channel
def test_email_then_whatsapp_same_day_both_send(client, create_user, get_headers):
    headers, client_id = _setup(client, create_user, get_headers, phone="0550550550")
    inv = client.post("/api/invoices", json=_invoice(client_id), headers=headers).json()["id"]

    email = client.post(f"/api/invoices/{inv}/reminders", json={"channel": "email"}, headers=headers).json()
    wa = client.post(f"/api/invoices/{inv}/reminders", json={"channel": "whatsapp"}, headers=headers).json()
    assert email["status"] == "sent"
    assert wa["status"] == "sent" and wa["link"].startswith("https://wa.me/")

    again = client.post(f"/api/invoices/{inv}/reminders", json={"channel": "whatsapp"}, headers=headers).json()
    assert again["status"] == "skipped"


def test_failed_reminder_can_be_retried(client, create_user, get_headers):
    headers, client_id = _setup(client, create_user, get_headers)  # no phone -> whatsapp fails
    inv = client.post("/api/invoices", json=_invoice(client_id), headers=headers).json()["id"]
    first = client.post(f"/api/invoices/{inv}/reminders", json={"channel": "whatsapp"}, headers=headers).json()
    second = client.post(f"/api/invoices/{inv}/reminders", json={"channel": "whatsapp"}, headers=headers).json()
    assert first["status"] == "failed" and second["status"] == "failed"  # not 'skipped'


# 4. Channel is a closed set
def test_unknown_channel_rejected(client, create_user, get_headers):
    headers, client_id = _setup(client, create_user, get_headers)
    inv = client.post("/api/invoices", json=_invoice(client_id), headers=headers).json()["id"]
    assert client.post(f"/api/invoices/{inv}/reminders", json={"channel": "sms"}, headers=headers).status_code == 422


# 5. Honest about log-only email
def test_email_without_smtp_is_flagged_as_logged_only(client, create_user, get_headers):
    headers, client_id = _setup(client, create_user, get_headers)
    inv = client.post("/api/invoices", json=_invoice(client_id), headers=headers).json()["id"]
    r = client.post(f"/api/invoices/{inv}/reminders", json={}, headers=headers).json()
    assert r["status"] == "sent"
    assert "not configured" in r["error"]
