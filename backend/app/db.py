from datetime import datetime, timezone
from typing import Generator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from .config import settings

def utcnow() -> datetime:
    """Naive UTC 'now' (replacement for the deprecated datetime.utcnow()).

    Naive on purpose: every DateTime column is TIMESTAMP WITHOUT TIME ZONE holding UTC, so mixing in
    tz-aware datetimes would break comparisons.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


# pool_pre_ping: a managed Postgres drops idle connections; check before reusing one instead of failing a request
engine = create_engine(settings.database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Stable constraint names, so Alembic migrations can drop or alter them later.
# (Check constraints are left to Postgres's default naming, e.g. invoices_status_check.)
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
Base = declarative_base(metadata=MetaData(naming_convention=NAMING_CONVENTION))

# Dependency to get DB session
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# The schema is managed by Alembic: run `alembic upgrade head` (see backend/alembic/).
