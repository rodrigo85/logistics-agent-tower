"""
Database engine and session management.

Supports PostgreSQL (Docker / Cloud SQL) and SQLite (local development and tests).
The URL is resolved by `Settings.resolved_database_url`.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from logistics_tower.config import settings
from logistics_tower.db.models import Base

DATABASE_URL = settings.resolved_database_url
_IS_SQLITE = DATABASE_URL.startswith("sqlite")

if _IS_SQLITE:
    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=not _IS_SQLITE,
    connect_args={"check_same_thread": False} if _IS_SQLITE else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create all tables defined in `models` (idempotent)."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI / service dependency yielding a scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
