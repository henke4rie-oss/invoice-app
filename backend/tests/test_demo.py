"""Demo mode: shared pre-filled account, safe by construction."""
from pathlib import Path

import pytest

from app.config import settings
from app.services import demo_service
from app.services.demo_service import DEMO_EMAIL

ASSET = Path(__file__).resolve().parent.parent / "app" / "demo_assets" / "northwind-logo.png"


@pytest.fixture(autouse=True)
def demo_on(client, monkeypatch):
    # After `client`: app startup ran with the demo off, so nothing was seeded outside the test transaction
    monkeypatch.setattr(settings, "demo_enabled", True)


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _demo_token(client):
    response = client.post("/api/auth/demo")
    assert response.status_code == 200
    return response.json()["access_token"]


def _all(client, token, path):
    return client.get(f"/api/{path}?limit=100", headers=_headers(token)).json()


def test_demo_login_returns_working_token_and_flags_user(client):
    token = _demo_token(client)
    me = client.get("/api/auth/me", headers=_headers(token))
    assert me.status_code == 200
    assert me.json()["email"] == DEMO_EMAIL
    assert me.json()["is_demo"] is True


def test_demo_account_is_seeded_with_realistic_data(client):
    token = _demo_token(client)
    assert len(_all(client, token, "clients")) == 6
    invoices = _all(client, token, "invoices")
    assert len(invoices) == 15
    assert {i["status"] for i in invoices} == {"draft", "sent", "overdue", "paid", "cancelled"}
    assert len({i["currency"] for i in invoices}) >= 3
    assert len(_all(client, token, "reminders")) >= 8
    profile = client.get("/api/profile", headers=_headers(token)).json()
    assert profile["business_name"] == demo_service.DEMO_BUSINESS_NAME


def test_repeated_demo_login_does_not_reseed_or_duplicate(client):
    first = _demo_token(client)
    client.post("/api/clients", json={"name": "Visitor Added"}, headers=_headers(first))
    second = _demo_token(client)
    names = [c["name"] for c in _all(client, second, "clients")]
    assert "Visitor Added" in names  # shared account: visitors see each other's changes until the daily reset
    assert len(names) == 7


def test_reset_is_idempotent_and_wipes_visitor_changes(client, db_session):
    token = _demo_token(client)
    client.post("/api/clients", json={"name": "Visitor Added"}, headers=_headers(token))
    invoices = _all(client, token, "invoices")
    client.delete(f"/api/invoices/{invoices[0]['id']}", headers=_headers(token))
    client.put("/api/profile", json={"business_name": "Defaced"}, headers=_headers(token))

    for _ in range(2):  # twice: running the reset again must not duplicate anything
        demo_id = demo_service.reset_demo_data(db_session).id

    me = client.get("/api/auth/me", headers=_headers(token))
    assert me.status_code == 200 and me.json()["id"] == demo_id  # same user, old token still valid
    assert len(_all(client, token, "clients")) == 6
    assert len(_all(client, token, "invoices")) == 15
    assert client.get("/api/profile", headers=_headers(token)).json()["business_name"] == demo_service.DEMO_BUSINESS_NAME


def test_demo_data_is_isolated_from_real_users(client, db_session, create_user, get_headers):
    _, _, real_token = create_user()
    client.post("/api/clients", json={"name": "My Real Client"}, headers=get_headers(real_token))
    demo_token = _demo_token(client)

    assert [c["name"] for c in _all(client, real_token, "clients")] == ["My Real Client"]
    assert _all(client, real_token, "invoices") == []

    demo_service.reset_demo_data(db_session)
    assert [c["name"] for c in _all(client, real_token, "clients")] == ["My Real Client"]  # reset never touches real users
    assert len(_all(client, demo_token, "clients")) == 6


def test_demo_email_is_reserved_for_registration(client):
    response = client.post("/api/auth/register", json={"email": DEMO_EMAIL, "password": "longenough1"})
    assert response.status_code == 400
    response = client.post("/api/auth/register", json={"email": DEMO_EMAIL.upper(), "password": "longenough1"})
    assert response.status_code == 400


def test_demo_account_cannot_be_logged_into_with_a_password(client):
    _demo_token(client)
    for guess in ("password", "demo1234", "longenough1", "example.com"):
        response = client.post("/api/auth/login", json={"email": DEMO_EMAIL, "password": guess})
        assert response.status_code == 401


def test_regular_account_with_demo_email_is_never_overwritten(client, db_session):
    """Defensive: if a normal user somehow owns the address, demo mode refuses instead of wiping it."""
    from app.models import User
    from app.auth import hash_password
    db_session.add(User(email=DEMO_EMAIL, password_hash=hash_password("realpassword1"), is_demo=False))
    db_session.commit()
    response = client.post("/api/auth/demo")
    assert response.status_code == 503
    login = client.post("/api/auth/login", json={"email": DEMO_EMAIL, "password": "realpassword1"})
    assert login.status_code == 200  # untouched


def test_demo_endpoint_404_when_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "demo_enabled", False)
    assert client.post("/api/auth/demo").status_code == 404


def test_demo_email_reminders_never_use_smtp(client, monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.invalid")  # SMTP "configured"

    def boom(*args, **kwargs):
        raise AssertionError("demo account tried to open an SMTP connection")
    monkeypatch.setattr("app.services.reminder_service.smtplib.SMTP", boom)

    token = _demo_token(client)
    open_invoice = next(i for i in _all(client, token, "invoices") if i["status"] == "sent")
    response = client.post(f"/api/invoices/{open_invoice['id']}/reminders", json={"channel": "email"}, headers=_headers(token))
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "sent"
    assert "not actually delivered" in body["error"]


def test_scheduled_reminder_run_skips_demo_user(client, db_session, monkeypatch):
    from app.services import scheduler
    _demo_token(client)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db_session)
    calls = []
    monkeypatch.setattr(scheduler, "trigger_overdue_reminders", lambda db, user_id: calls.append(user_id) or {})
    scheduler._run_daily_reminders()
    assert calls == []


# ---------- "Reset demo data" button ----------

def test_reset_endpoint_restores_the_seed_and_removes_visitor_changes(client):
    token = _demo_token(client)
    me = client.get("/api/auth/me", headers=_headers(token)).json()
    logos = Path(settings.logos_dir)

    client.post("/api/clients", json={"name": "Visitor Added"}, headers=_headers(token))
    client.put("/api/profile", json={"business_name": "Defaced"}, headers=_headers(token))
    jpeg = b"\xff\xd8\xff" + b"0" * 32  # a different extension than the seeded .png
    assert client.post("/api/profile/logo", files={"file": ("l.jpg", jpeg, "image/jpeg")}, headers=_headers(token)).status_code == 200
    visitor_logo = logos / f"{me['id']}.jpg"
    assert visitor_logo.exists()
    invoices = _all(client, token, "invoices")
    client.delete(f"/api/invoices/{invoices[0]['id']}", headers=_headers(token))

    response = client.post("/api/auth/demo/reset", headers=_headers(token))
    assert response.status_code == 200

    assert len(_all(client, token, "clients")) == 6
    assert len(_all(client, token, "invoices")) == 15
    profile = client.get("/api/profile", headers=_headers(token)).json()
    assert profile["business_name"] == demo_service.DEMO_BUSINESS_NAME
    assert not visitor_logo.exists()  # the visitor's upload is gone...
    assert profile["logo_url"] is not None  # ...and the example logo is back, byte for byte
    assert client.get("/api/profile/logo", headers=_headers(token)).content == ASSET.read_bytes()
    assert client.get("/api/auth/me", headers=_headers(token)).status_code == 200  # same session keeps working


def test_reset_overwriting_a_visitor_png_restores_the_example_logo(client):
    token = _demo_token(client)
    me = client.get("/api/auth/me", headers=_headers(token)).json()
    visitor_png = b"\x89PNG\r\n\x1a\n" + b"visitor" * 8
    assert client.post("/api/profile/logo", files={"file": ("mine.png", visitor_png, "image/png")}, headers=_headers(token)).status_code == 200
    assert client.get("/api/profile/logo", headers=_headers(token)).content == visitor_png  # same file name as the seeded logo
    assert client.post("/api/auth/demo/reset", headers=_headers(token)).status_code == 200
    assert client.get("/api/profile/logo", headers=_headers(token)).content == ASSET.read_bytes()


def test_reset_endpoint_is_for_the_demo_account_only(client, create_user, get_headers):
    _, _, real_token = create_user()
    client.post("/api/clients", json={"name": "Mine"}, headers=get_headers(real_token))
    assert client.post("/api/auth/demo/reset", headers=get_headers(real_token)).status_code == 403
    assert [c["name"] for c in _all(client, real_token, "clients")] == ["Mine"]
    assert client.post("/api/auth/demo/reset").status_code == 401


def test_reset_endpoint_404_when_demo_disabled(client, monkeypatch):
    token = _demo_token(client)
    monkeypatch.setattr(settings, "demo_enabled", False)
    assert client.post("/api/auth/demo/reset", headers=_headers(token)).status_code == 404


# ---------- example logo ----------

def test_demo_business_starts_with_the_example_logo(client):
    token = _demo_token(client)
    profile = client.get("/api/profile", headers=_headers(token)).json()
    assert profile["logo_url"]
    logo = client.get("/api/profile/logo", headers=_headers(token))
    assert logo.status_code == 200
    assert logo.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert logo.content == ASSET.read_bytes()


def test_repeated_resets_leave_exactly_one_logo_file(client, db_session):
    token = _demo_token(client)
    demo_id = client.get("/api/auth/me", headers=_headers(token)).json()["id"]
    for _ in range(3):
        demo_service.reset_demo_data(db_session)
    assert sorted(p.name for p in Path(settings.logos_dir).glob(f"{demo_id}.*")) == [f"{demo_id}.png"]


def test_a_missing_logo_asset_never_breaks_seeding(client, monkeypatch, tmp_path):
    monkeypatch.setattr(demo_service, "_DEMO_LOGO", tmp_path / "does-not-exist.png")
    token = _demo_token(client)  # seeds on first use
    assert len(_all(client, token, "invoices")) == 15
    assert client.get("/api/profile", headers=_headers(token)).json()["logo_url"] is None
