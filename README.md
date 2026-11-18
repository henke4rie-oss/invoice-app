# Invoice Reminder SaaS MVP

## Overview

A minimal invoice reminder SaaS built with FastAPI + SQLite. Track-only reminders (no real email), manual + daily scheduled triggers. Per-user data isolation via JWT auth.

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
- Dashboard summary (counts + outstanding per currency)
- SMTP email delivery (configurable via SMTP_* env vars) and free WhatsApp reminders via wa.me links
- Security features: JWT auth, rate limiting, security headers, input validation, file upload validation
- Settings tab (business name + logo upload) and branded invoice view with print
- Country/currency selector

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

Single file `frontend/index.html`. Uses fetch to `/api/...` with Authorization header from localStorage. Blue/purple palette, no red accents.

## License

MIT
