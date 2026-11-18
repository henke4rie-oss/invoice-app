# Invoice Reminder SaaS MVP

## Overview

A minimal invoice reminder SaaS built with FastAPI + SQLite. Email reminders (real SMTP delivery is opt-in through `ALLOW_OUTBOUND_EMAIL`) and WhatsApp links, manual and daily scheduled triggers, and a one-click **live demo**: a shared, pre-filled account that resets every hour. Per-user data isolation via JWT auth.

<!-- TODO: live demo link + screenshot -->

## Quick start

Want to look around without signing up? Click **Try the live demo**. Other visitors share that account and can see what you change, so the banner says so and gives you a **Reset demo data** button.

## Files

- `backend/` – FastAPI backend (Python, FastAPI + SQLAlchemy + Pydantic)
- `frontend/index.html` – Single-file HTML/JS/CSS dashboard
- `data/app.db` – SQLite database (gitignored)

## Setup

1. **Install dependencies** (once):
   ```bash
   cd backend
   python -m pip install -r requirements.txt
   ```
2. **Environment** (create `.env` from `.env.example`):
   ```bash
   cp .env.example .env
   ```
   Adjust `SECRET_KEY`, `DATABASE_URL`, `CORS_ORIGINS` as needed.
3. **Initialize DB and run**:
   ```bash
   cd backend
   python -m uvicorn app.main:app --reload
   ```
4. **Open the dashboard**:
   Open `frontend/index.html` in a browser. Use `http://localhost:8000` as base if CORS is configured.

## Features

- User registration / login (JWT bearer tokens)
- CRUD clients and invoices
- Reminders (track sent/failed/skipped), manual trigger, daily scheduler (09:00 UTC) for overdue unpaid invoices
- Daily reminder cap per user (`MAX_REMINDERS_PER_DAY`)
- Dashboard summary (counts + outstanding per currency)
- SMTP email delivery (opt-in with `ALLOW_OUTBOUND_EMAIL`, configured via `SMTP_*`) and free WhatsApp reminders via wa.me links
- Demo mode: shared pre-filled account, reset hourly, never sends real email
- Account deletion (password-confirmed; removes all of the user's data and logo)
- Dark-by-default UI with a light toggle, responsive layout (tables become cards on phones), printable invoices
- Settings tab (business name + logo upload) and branded invoice view with print
- Country/currency selector
- Security: bcrypt password hashing (72-byte limit enforced), tokens bound to the account and valid for 2 hours, rate limits on login, delete-account and demo reset, client IP that cannot be spoofed (`TRUSTED_PROXY_HOPS`), HSTS and CSP headers, input validation, file upload validation

## Configuration

Copy `backend/.env.example` to `backend/.env`. Every variable is optional for local development.

| Variable | Default | What it does |
|---|---|---|
| `SECRET_KEY` | dev value | JWT signing key. Must be 32+ characters when `DEBUG=false`, or the app refuses to start. |
| `DATABASE_URL` | `sqlite:///./data/app.db` | Database location. |
| `DEBUG` | `true` | Turns off the auth rate limits and HSTS, and enables `/docs`. Set `false` in production. |
| `CORS_ORIGINS` | localhost list | Comma-separated origins allowed to call the API. |
| `ACCESS_TOKEN_MINUTES` | `120` | Login token lifetime. |
| `TRUSTED_PROXY_HOPS` | `0` | Reverse proxies in front of the app. Behind Render, set `1`. |
| `AUTH_RATE_LIMIT` / `AUTH_RATE_WINDOW` | `10` / `900` | Login and register attempts per IP per window (seconds). |
| `DEMO_ENABLED` | `true` | Shows the live demo and its hourly reset. |
| `LOGOS_DIR` | `backend/data/logos` | Where uploaded business logos are stored. |
| `SCHEDULER_ENABLED` / `SCHEDULER_TIME` | `true` / `09:00` | Daily overdue-reminder job (UTC). |
| `ALLOW_OUTBOUND_EMAIL` | `false` | Sends real SMTP mail. Leave `false` to only log reminders. |
| `MAX_REMINDERS_PER_DAY` | `50` | Reminder deliveries allowed per user per UTC day. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`, `SMTP_USE_TLS` | empty / `587` / … / `true` | SMTP server used when `ALLOW_OUTBOUND_EMAIL=true`. |

## Deploying on Render

The `render.yaml` blueprint deploys the Docker image on Render's free plan. Be aware of the following:

- **Real accounts are not durable.** The free plan has no persistent disk, so the SQLite database and uploaded logos are wiped on every redeploy or restart. The demo account re-seeds itself at startup.
- **Check the proxy setting after the first deploy.** Behind Render's proxy, `TRUSTED_PROXY_HOPS=1` makes rate limits count the real client. To check, send 35 login attempts with a different forged `X-Forwarded-For` each time:
  ```bash
  for i in $(seq 1 35); do curl -s -o /dev/null -w "%{http_code} " -XPOST https://YOUR-APP.onrender.com/api/auth/login \
    -H 'content-type: application/json' -H "X-Forwarded-For: 6.6.6.$i" \
    -d '{"email":"a@example.com","password":"wrongpass1"}'; done
  ```
  Expect 401s, then 429s after the limit (30 on Render). If you never see a 429, raise `TRUSTED_PROXY_HOPS` until you do. If they start too early, the value is too high.
- **Existing sessions end once** after the token change, since older tokens are not tied to an account and are rejected.

## Backend structure

- `app/main.py` – FastAPI app, CORS, routers, lifespan (DB init + scheduler)
- `app/config.py` – pydantic-settings from env
- `app/db.py` – SQLAlchemy engine, SessionLocal, init_db, FK pragma
- `app/models.py` – SQLAlchemy ORM models
- `app/schemas.py` – Pydantic v2 schemas
- `app/auth.py` – JWT + bcrypt helpers
- `app/deps.py` – get_current_user dependency
- `app/repositories/` – SQLAlchemy CRUD reps
- `app/services/` – business logic, status transitions, reminder orchestration, APScheduler job
- `app/routers/` – route handlers

## Frontend

Single file `frontend/index.html`. Uses fetch to `/api/...` with Authorization header from localStorage. Blue/purple palette, no red accents. Dark by default; the theme toggle is remembered in localStorage.

## License

MIT
