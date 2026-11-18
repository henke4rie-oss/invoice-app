"""Phase 3 hardening: rate-limit IP spoofing, token lifetime, password byte limit,
account deletion, daily reminder cap and opt-in outbound email."""
import time
from datetime import timedelta
from pathlib import Path

import pytest

from app import auth
from app.config import settings
from app.db import utcnow
from app.models import Client, Invoice, Reminder, User
import app.main as main_module

BAD_LOGIN = {"email": "nobody@example.com", "password": "wrongpass1"}


def _h(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- rate limiter: client IP cannot be spoofed ----------

@pytest.fixture
def limited(monkeypatch, client):
    """Rate limiting on (it is off in debug), 3 attempts per window, clean bucket store."""
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "auth_rate_limit", 3)
    monkeypatch.setattr(settings, "auth_rate_window", 900)
    main_module.rate_limit_data.clear()
    yield
    main_module.rate_limit_data.clear()


def _attempt(client, xff=None):
    headers = {"X-Forwarded-For": xff} if xff else {}
    return client.post("/api/auth/login", json=BAD_LOGIN, headers=headers).status_code


def test_forged_xff_does_not_bypass_limit_without_trusted_proxy(client, limited, monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_hops", 0)
    codes = [_attempt(client, f"203.0.113.{i}") for i in range(5)]  # a new fake IP every time
    assert codes == [401, 401, 401, 429, 429]


def test_forged_left_entries_ignored_behind_one_trusted_proxy(client, limited, monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_hops", 1)
    # The proxy appended the real address (198.51.100.7); the client forged everything to its left
    codes = [_attempt(client, f"6.6.6.{i}, 198.51.100.7") for i in range(5)]
    assert codes == [401, 401, 401, 429, 429]


def test_different_real_clients_have_separate_buckets_behind_proxy(client, limited, monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_hops", 1)
    for _ in range(3):
        assert _attempt(client, "198.51.100.7") == 401
    assert _attempt(client, "198.51.100.7") == 429
    assert _attempt(client, "198.51.100.8") == 401  # someone else is not locked out


def test_missing_or_short_xff_falls_back_to_socket_address(client, limited, monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_hops", 2)
    # header has 1 entry but 2 hops are expected: it cannot be trusted, so everyone shares the peer bucket
    codes = [_attempt(client, f"1.1.1.{i}") for i in range(4)]
    assert codes == [401, 401, 401, 429]


# ---------- token lifetime ----------

def test_default_token_lifetime_is_two_hours():
    assert settings.access_token_minutes == 120
    payload = auth.verify_token(auth.create_access_token({"sub": "1"}))
    assert 119 * 60 <= payload["exp"] - time.time() <= 121 * 60


def test_token_lifetime_is_configurable(monkeypatch):
    monkeypatch.setattr(settings, "access_token_minutes", 5)
    payload = auth.verify_token(auth.create_access_token({"sub": "1"}))
    assert 4 * 60 <= payload["exp"] - time.time() <= 6 * 60


def test_expired_token_is_rejected(client, create_user):
    _, _, _ = create_user()
    user_token = auth.create_access_token({"sub": "1"}, expires_delta=timedelta(minutes=-1))
    assert client.get("/api/auth/me", headers=_h(user_token)).status_code == 401


# ---------- bcrypt's 72-BYTE limit must be a 422, not a 500 ----------

def test_multibyte_password_over_72_bytes_is_rejected_cleanly(client):
    long_pw = "é" * 40  # 40 characters but 80 bytes
    for path in ("/api/auth/register", "/api/auth/login"):
        response = client.post(path, json={"email": "multi@example.com", "password": long_pw})
        assert response.status_code == 422, path


def test_password_at_exactly_72_bytes_still_works(client):
    pw = "é" * 36  # 72 bytes
    assert client.post("/api/auth/register", json={"email": "edge@example.com", "password": pw}).status_code == 201
    assert client.post("/api/auth/login", json={"email": "edge@example.com", "password": pw}).status_code == 200


# ---------- account deletion ----------

def _seed(client, token, number="INV-1", due_days=-5, client_email="c@example.com"):
    c = client.post("/api/clients", json={"name": "C " + number, "email": client_email}, headers=_h(token)).json()
    due = (utcnow() + timedelta(days=due_days)).isoformat()
    inv = client.post("/api/invoices", json={
        "client_id": c["id"], "number": number, "amount_cents": 10000, "currency": "USD",
        "issue_date": (utcnow() - timedelta(days=30)).isoformat(), "due_date": due}, headers=_h(token))
    assert inv.status_code == 201
    return c["id"], inv.json()["id"]


def _delete_account(client, token, password):
    return client.request("DELETE", "/api/profile", json={"password": password}, headers=_h(token))


def test_delete_account_requires_authentication(client):
    assert client.request("DELETE", "/api/profile", json={"password": "whatever1"}).status_code == 401


def test_delete_account_needs_a_password(client, create_user):
    _, _, token = create_user()
    assert client.request("DELETE", "/api/profile", headers=_h(token)).status_code == 422
    assert client.request("DELETE", "/api/profile", json={}, headers=_h(token)).status_code == 422


def test_delete_account_wrong_password_changes_nothing(client, create_user):
    email, password, token = create_user()
    _seed(client, token)
    response = _delete_account(client, token, "not-the-password")
    assert response.status_code == 403  # not 401: the UI would read that as "session expired"
    assert client.get("/api/auth/me", headers=_h(token)).status_code == 200
    assert len(client.get("/api/invoices", headers=_h(token)).json()) == 1


def test_delete_account_removes_everything_and_only_that_user(client, create_user, db_session):
    email_a, pw_a, token_a = create_user()
    email_b, pw_b, token_b = create_user()
    _, inv_a = _seed(client, token_a, "A-1")
    _seed(client, token_b, "B-1")
    client.post(f"/api/invoices/{inv_a}/reminders", json={"channel": "email"}, headers=_h(token_a))  # reminder row (FK child)
    user_a_id = db_session.query(User).filter(User.email == email_a).one().id

    assert _delete_account(client, token_a, pw_a).status_code == 204

    db_session.expire_all()
    assert db_session.query(User).filter(User.id == user_a_id).count() == 0
    assert db_session.query(Client).filter(Client.user_id == user_a_id).count() == 0
    assert db_session.query(Invoice).filter(Invoice.user_id == user_a_id).count() == 0
    assert db_session.query(Reminder).filter(Reminder.invoice_id == inv_a).count() == 0
    # the old token and password are dead
    assert client.get("/api/auth/me", headers=_h(token_a)).status_code == 401
    assert client.post("/api/auth/login", json={"email": email_a, "password": pw_a}).status_code == 401
    # the other user is untouched
    assert len(client.get("/api/invoices", headers=_h(token_b)).json()) == 1
    assert client.get("/api/auth/me", headers=_h(token_b)).status_code == 200


def test_delete_account_removes_uploaded_logo_file(client, create_user):
    _, password, token = create_user()
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 32
    up = client.post("/api/profile/logo", files={"file": ("logo.png", png, "image/png")}, headers=_h(token))
    assert up.status_code == 200
    logos = Path(__file__).resolve().parent.parent / "data" / "logos"
    user_id = client.get("/api/auth/me", headers=_h(token)).json()["id"]
    assert (logos / f"{user_id}.png").exists()
    assert _delete_account(client, token, password).status_code == 204
    assert not (logos / f"{user_id}.png").exists()


def test_demo_account_cannot_be_deleted(client, monkeypatch):
    monkeypatch.setattr(settings, "demo_enabled", True)
    token = client.post("/api/auth/demo").json()["access_token"]
    assert _delete_account(client, token, "anything1").status_code == 403
    assert client.get("/api/auth/me", headers=_h(token)).status_code == 200


def test_multibyte_password_on_delete_is_422_not_500(client, create_user):
    _, _, token = create_user()
    assert _delete_account(client, token, "é" * 40).status_code == 422


# ---------- daily reminder cap ----------

def test_daily_cap_blocks_further_reminders_with_429(client, create_user, monkeypatch):
    monkeypatch.setattr(settings, "max_reminders_per_day", 2)
    _, _, token = create_user()
    ids = [_seed(client, token, f"CAP-{i}", due_days=10)[1] for i in range(3)]
    codes = [client.post(f"/api/invoices/{i}/reminders", json={"channel": "email"}, headers=_h(token)).status_code for i in ids]
    assert codes == [201, 201, 429]
    detail = client.post(f"/api/invoices/{ids[2]}/reminders", json={"channel": "email"}, headers=_h(token)).json()["detail"]
    assert "Daily reminder limit" in detail


def test_duplicate_skips_do_not_use_up_the_cap(client, create_user, monkeypatch):
    monkeypatch.setattr(settings, "max_reminders_per_day", 1)
    _, _, token = create_user()
    first = _seed(client, token, "DUP-1", due_days=10)[1]
    second = _seed(client, token, "DUP-2", due_days=10)[1]
    assert client.post(f"/api/invoices/{first}/reminders", json={"channel": "email"}, headers=_h(token)).json()["status"] == "sent"
    again = client.post(f"/api/invoices/{first}/reminders", json={"channel": "email"}, headers=_h(token))
    assert again.status_code == 201 and again.json()["status"] == "skipped"  # dedupe answers before the cap
    assert client.post(f"/api/invoices/{second}/reminders", json={"channel": "email"}, headers=_h(token)).status_code == 429


def test_cap_is_per_user(client, create_user, monkeypatch):
    monkeypatch.setattr(settings, "max_reminders_per_day", 1)
    _, _, token_a = create_user()
    _, _, token_b = create_user()
    a1 = _seed(client, token_a, "PA-1", due_days=10)[1]
    a2 = _seed(client, token_a, "PA-2", due_days=10)[1]
    b1 = _seed(client, token_b, "PB-1", due_days=10)[1]
    assert client.post(f"/api/invoices/{a1}/reminders", json={"channel": "email"}, headers=_h(token_a)).status_code == 201
    assert client.post(f"/api/invoices/{a2}/reminders", json={"channel": "email"}, headers=_h(token_a)).status_code == 429
    assert client.post(f"/api/invoices/{b1}/reminders", json={"channel": "email"}, headers=_h(token_b)).status_code == 201


def test_run_due_stops_at_the_cap_and_reports_it(client, create_user, monkeypatch):
    monkeypatch.setattr(settings, "max_reminders_per_day", 1)
    _, _, token = create_user()
    for i in range(3):
        _seed(client, token, f"DUE-{i}", due_days=-5)
    result = client.post("/api/reminders/run-due", headers=_h(token)).json()
    assert result["sent"] == 1
    assert result["limited"] is True


def test_run_due_reports_not_limited_normally(client, create_user):
    _, _, token = create_user()
    _seed(client, token, "DUE-OK", due_days=-5)
    result = client.post("/api/reminders/run-due", headers=_h(token)).json()
    assert result["sent"] == 1 and result["limited"] is False


# ---------- outbound email is opt-in ----------

class FakeSMTP:
    sent = []

    def __init__(self, host, port):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        pass

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


@pytest.fixture
def fake_smtp(monkeypatch):
    FakeSMTP.sent = []
    monkeypatch.setattr("app.services.reminder_service.smtplib.SMTP", FakeSMTP)
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.invalid")
    return FakeSMTP


def test_smtp_configured_but_not_allowed_only_logs(client, create_user, fake_smtp, monkeypatch):
    monkeypatch.setattr(settings, "allow_outbound_email", False)
    _, _, token = create_user()
    inv = _seed(client, token, "OUT-1", due_days=10)[1]
    body = client.post(f"/api/invoices/{inv}/reminders", json={"channel": "email"}, headers=_h(token)).json()
    assert body["status"] == "sent"
    assert "ALLOW_OUTBOUND_EMAIL" in body["error"]
    assert fake_smtp.sent == []  # nothing left the building


def test_smtp_used_only_when_explicitly_allowed(client, create_user, fake_smtp, monkeypatch):
    monkeypatch.setattr(settings, "allow_outbound_email", True)
    _, _, token = create_user()
    inv = _seed(client, token, "OUT-2", due_days=10, client_email="payer@example.com")[1]
    body = client.post(f"/api/invoices/{inv}/reminders", json={"channel": "email"}, headers=_h(token)).json()
    assert body["status"] == "sent" and not body["error"]
    assert len(fake_smtp.sent) == 1 and fake_smtp.sent[0]["To"] == "payer@example.com"


def test_no_smtp_host_keeps_the_original_log_message(client, create_user, monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "")
    _, _, token = create_user()
    inv = _seed(client, token, "OUT-3", due_days=10)[1]
    body = client.post(f"/api/invoices/{inv}/reminders", json={"channel": "email"}, headers=_h(token)).json()
    assert "SMTP_HOST unset" in body["error"]


# ---------- regression: an invoice that has reminders must be deletable ----------

def test_invoice_with_reminders_can_be_deleted(client, create_user, db_session):
    _, _, token = create_user()
    _, inv = _seed(client, token, "DEL-1", due_days=10)
    assert client.post(f"/api/invoices/{inv}/reminders", json={"channel": "email"}, headers=_h(token)).status_code == 201
    assert db_session.query(Reminder).filter(Reminder.invoice_id == inv).count() == 1

    response = client.delete(f"/api/invoices/{inv}", headers=_h(token))
    assert response.status_code == 204  # used to be a 500 (NOT NULL constraint failed: reminders.invoice_id)

    db_session.expire_all()
    assert db_session.query(Reminder).filter(Reminder.invoice_id == inv).count() == 0
    assert client.get(f"/api/invoices/{inv}", headers=_h(token)).status_code == 404


# ---------- Phase 3b: tokens are bound to the account they were issued for ----------

def test_new_databases_never_reuse_user_ids(client, create_user):
    from app.models import User as UserModel
    assert UserModel.__table__.kwargs.get("sqlite_autoincrement") is True
    first_email, first_pw, token = create_user()
    first_id = client.get("/api/auth/me", headers=_h(token)).json()["id"]
    assert _delete_account(client, token, first_pw).status_code == 204
    _, _, token2 = create_user()
    assert client.get("/api/auth/me", headers=_h(token2)).json()["id"] != first_id


def test_deleted_users_token_is_dead_even_if_the_id_is_reused(client, create_user, db_session):
    """Simulates a database that reuses the id (older SQLite tables without AUTOINCREMENT do)."""
    from app.auth import hash_password
    email, password, old_token = create_user()
    victim_id = client.get("/api/auth/me", headers=_h(old_token)).json()["id"]
    assert _delete_account(client, old_token, password).status_code == 204

    db_session.add(User(id=victim_id, email="newcomer@example.com", password_hash=hash_password("longenough2"), created_at=utcnow()))
    db_session.commit()

    assert client.get("/api/auth/me", headers=_h(old_token)).status_code == 401  # used to return the newcomer's profile
    login = client.post("/api/auth/login", json={"email": "newcomer@example.com", "password": "longenough2"})
    me = client.get("/api/auth/me", headers=_h(login.json()["access_token"]))
    assert me.status_code == 200 and me.json()["id"] == victim_id  # the newcomer's own token works


def test_token_without_or_with_wrong_stamp_is_rejected(client, create_user):
    _, _, token = create_user()
    user_id = client.get("/api/auth/me", headers=_h(token)).json()["id"]
    assert client.get("/api/auth/me", headers=_h(token)).status_code == 200
    no_stamp = auth.create_access_token({"sub": str(user_id)})  # e.g. issued before this fix was deployed
    wrong_stamp = auth.create_access_token({"sub": str(user_id), "uat": 12345})
    assert client.get("/api/auth/me", headers=_h(no_stamp)).status_code == 401
    assert client.get("/api/auth/me", headers=_h(wrong_stamp)).status_code == 401


# ---------- Phase 3b: HSTS survives not trusting proxy headers ----------

def test_hsts_is_sent_outside_debug_even_over_plain_http(client, monkeypatch):
    monkeypatch.setattr(settings, "debug", False)  # behind Render the app itself only ever sees http
    assert "max-age=31536000" in client.get("/health").headers["strict-transport-security"]


def test_hsts_is_not_sent_in_debug_over_http(client, monkeypatch):
    monkeypatch.setattr(settings, "debug", True)
    assert "strict-transport-security" not in client.get("/health").headers


# ---------- Phase 3b: delete-account and demo-reset are rate limited, each with its own budget ----------

def test_delete_account_password_guessing_is_rate_limited(client, create_user, limited):
    _, _, token = create_user()
    codes = [_delete_account(client, token, "wrong-password1").status_code for _ in range(5)]
    assert codes == [403, 403, 403, 429, 429]


def test_demo_reset_is_rate_limited(client, limited, monkeypatch):
    monkeypatch.setattr(settings, "demo_enabled", True)
    token = client.post("/api/auth/demo").json()["access_token"]
    codes = [client.post("/api/auth/demo/reset", headers=_h(token)).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]


def test_exhausting_login_attempts_does_not_block_demo_reset(client, limited, monkeypatch):
    monkeypatch.setattr(settings, "demo_enabled", True)
    assert [_attempt(client) for _ in range(4)] == [401, 401, 401, 429]  # login budget gone
    token = client.post("/api/auth/demo").json()["access_token"]
    assert client.post("/api/auth/demo/reset", headers=_h(token)).status_code == 200  # separate bucket


# ---------- Phase 3b: shared demo is exempt from the reminder cap ----------

def test_demo_visitors_cannot_exhaust_the_reminder_cap(client, monkeypatch):
    monkeypatch.setattr(settings, "demo_enabled", True)
    monkeypatch.setattr(settings, "max_reminders_per_day", 1)
    token = client.post("/api/auth/demo").json()["access_token"]
    sent = [i for i in client.get("/api/invoices?limit=100", headers=_h(token)).json() if i["status"] == "sent"]
    assert len(sent) >= 3
    codes = [client.post(f"/api/invoices/{i['id']}/reminders", json={"channel": "email"}, headers=_h(token)).status_code for i in sent[:3]]
    assert codes == [201, 201, 201]  # a real user with cap=1 would get 201, 429, 429


# ---------- Phase 3b: the demo is reset every hour ----------

def test_demo_reset_job_is_scheduled_hourly(monkeypatch):
    from app.services import scheduler
    jobs = []
    monkeypatch.setattr(scheduler.scheduler, "add_job", lambda func, trigger, **kw: jobs.append((func, trigger, kw)))
    monkeypatch.setattr(scheduler.scheduler, "start", lambda: None)

    monkeypatch.setattr(settings, "demo_enabled", True)
    scheduler.start_scheduler()
    demo_jobs = [j for j in jobs if j[0] is scheduler.reset_demo_job]
    assert len(demo_jobs) == 1
    _, trigger, kwargs = demo_jobs[0]
    assert trigger == "cron" and kwargs == {"minute": 0}  # no "hour": fires at minute 0 of every hour

    jobs.clear()
    monkeypatch.setattr(settings, "demo_enabled", False)
    scheduler.start_scheduler()
    assert not [j for j in jobs if j[0] is scheduler.reset_demo_job]
