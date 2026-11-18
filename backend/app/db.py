from datetime import datetime, timezone
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, declarative_base
from typing import Generator
from sqlalchemy.orm import Session
from .config import settings

def utcnow() -> datetime:
    """Naive UTC 'now' (replacement for the deprecated datetime.utcnow()).

    Naive on purpose: SQLite DateTime columns store naive values, so mixing in
    tz-aware datetimes would break comparisons.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False}
)

# SQLite: enable foreign keys
if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_conn, connection_record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Dependency to get DB session
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Initialize DB (create tables)
from . import models

def init_db():
    Base.metadata.create_all(bind=engine)
    
    # Guarded ALTERs to add columns to databases created before they existed
    for statement in (
        "ALTER TABLE clients ADD COLUMN phone VARCHAR",
        "ALTER TABLE users ADD COLUMN business_name VARCHAR",
        "ALTER TABLE users ADD COLUMN logo_path VARCHAR",
        "ALTER TABLE reminders ADD COLUMN link VARCHAR",
        "ALTER TABLE users ADD COLUMN is_demo BOOLEAN NOT NULL DEFAULT 0",
    ):
        try:
            with engine.begin() as conn:
                conn.execute(text(statement))
        except Exception:
            pass  # column already exists
