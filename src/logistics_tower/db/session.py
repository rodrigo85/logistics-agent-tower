"""
Database session and connection management for Logistics Control Tower.
Supports PostgreSQL (Docker / Cloud) and SQLite with automatic schema migration.
"""

import os
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from logistics_tower.config import settings
from logistics_tower.db.models import Base

# Database URL resolution:
# If DATABASE_URL is set (e.g. postgresql+psycopg://postgres:postgres@localhost:5432/logistics), use it.
# Otherwise, default to SQLite file inside project directory.
_DEFAULT_DB_FILE = settings.project_root / "data" / "logistics.db"
_DEFAULT_DB_FILE.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_DEFAULT_DB_FILE}")

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Creates all database tables defined in models."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI and service dependency to yield a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
