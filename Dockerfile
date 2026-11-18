FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBUG=false

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# The backend serves ../frontend, so keep the repo layout
COPY backend backend
COPY frontend frontend

# SQLite DB and uploaded logos live in backend/data (ephemeral unless a volume is mounted)
RUN useradd --create-home app && mkdir -p backend/data && chown -R app:app backend/data
USER app
WORKDIR /app/backend

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD python -c "import os,urllib.request as u; u.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8000'))"

# SECRET_KEY (>= 32 chars) must be provided at runtime: the app refuses to start with DEBUG=false otherwise.
# --no-proxy-headers: uvicorn must not rewrite the client address from X-Forwarded-For (with
# --forwarded-allow-ips='*' it would take the leftmost entry, which the client controls and could
# use to dodge the login rate limit). The app resolves the real client IP itself, using TRUSTED_PROXY_HOPS.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-proxy-headers"]
