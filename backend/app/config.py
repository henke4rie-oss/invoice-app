from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    secret_key: str = Field(default="dev-secret-change-in-production")
    database_url: str = Field(default="sqlite:///./data/app.db")
    cors_origins: str = Field(default="http://localhost,http://127.0.0.1,http://localhost:8000,http://127.0.0.1:8000,http://localhost:5500,http://127.0.0.1:5500,null")
    scheduler_time: str = Field(default="09:00")
    scheduler_enabled: bool = Field(default=True)
    # Auth endpoints (login/register): max requests per client IP per window (seconds). Ignored when DEBUG=true.
    auth_rate_limit: int = Field(default=10)
    auth_rate_window: int = Field(default=900)
    debug: bool = Field(default=True)
    # Access-token lifetime. Short on purpose: tokens live in localStorage and cannot be revoked server-side.
    access_token_minutes: int = Field(default=120)
    # Number of trusted reverse proxies in front of the app (0 = none, use the socket address).
    # With N > 0 the client IP is the Nth-from-right X-Forwarded-For entry, which the proxy chain appends
    # and a client cannot forge. Never trust the leftmost entry: the client controls it.
    trusted_proxy_hops: int = Field(default=0, ge=0)
    # Real SMTP delivery is opt-in: with SMTP_HOST set but this false, reminders are only logged.
    allow_outbound_email: bool = Field(default=False)
    # Per-user cap on reminder deliveries (sent + failed attempts) per UTC day.
    max_reminders_per_day: int = Field(default=50, ge=1)
    # Demo mode: a shared pre-filled account reachable via POST /api/auth/demo, reset every hour (UTC)
    demo_enabled: bool = Field(default=True)
    smtp_host: str = Field(default="")
    smtp_port: int = Field(default=587)
    smtp_user: str = Field(default="")
    smtp_pass: str = Field(default="")
    smtp_from: str = Field(default="")
    smtp_use_tls: bool = Field(default=True)

settings = Settings()
