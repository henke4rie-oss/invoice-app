from datetime import timedelta
from app.db import utcnow


def _invoice(client_id, number, cents, currency="USD", days=30):
    return {
        "client_id": client_id,
        "number": number,
        "amount_cents": cents,
        "currency": currency,
        "issue_date": utcnow().isoformat(),
        "due_date": (utcnow() + timedelta(days=days)).isoformat(),
    }


def test_dashboard_and_summary(client, create_user, get_headers):
    """Dashboard/summary aggregates are per-user and grouped correctly"""
    _, _, token = create_user()
    headers = get_headers(token)
    big = client.post("/api/clients", json={"name": "Big Spender"}, headers=headers).json()["id"]
    small = client.post("/api/clients", json={"name": "Small Fry"}, headers=headers).json()["id"]
    client.post("/api/invoices", json=_invoice(big, "D-1", 50000), headers=headers)
    client.post("/api/invoices", json=_invoice(big, "D-2", 25000, "EUR"), headers=headers)
    client.post("/api/invoices", json=_invoice(small, "D-3", 1000, days=-5), headers=headers)

    # Another user's data must not leak in
    _, _, other_token = create_user()
    other_client = client.post("/api/clients", json={"name": "Other"}, headers=get_headers(other_token)).json()["id"]
    client.post("/api/invoices", json=_invoice(other_client, "O-1", 999999), headers=get_headers(other_token))

    data = client.get("/api/dashboard/", headers=headers).json()
    assert data["total_clients"] == 2
    assert data["total_invoices"] == 3
    assert data["total_amount"] == 760.0
    assert data["total_overdue"] == 1
    assert data["recent_invoices_count"] == 3
    assert {i["client_name"] for i in data["recent_invoices"]} == {"Big Spender", "Small Fry"}
    assert data["top_clients"][0]["name"] == "Big Spender"
    assert data["top_clients"][0]["invoice_count"] == 2
    assert data["top_clients"][0]["total_amount"] == 750.0

    summary = client.get("/api/dashboard/summary", headers=headers).json()
    assert summary["total_invoices"] == 3
    assert summary["by_status"] == {"draft": 3}
    assert summary["outstanding_by_currency"] == {"USD": 51000, "EUR": 25000}
    assert summary["overdue_count"] == 1
    assert summary["reminders_sent_30d"] == 0
