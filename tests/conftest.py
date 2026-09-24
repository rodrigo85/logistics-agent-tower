"""
Pytest configuration and global fixtures.

Every test session runs against a throw-away SQLite database so the developer's
local `data/logistics.db` is never touched. The URL must be set *before* the
package is imported because the SQLAlchemy engine is created at import time.
"""

import os
import tempfile
from pathlib import Path

_TEST_DB_DIR = Path(tempfile.mkdtemp(prefix="logistics-tower-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TEST_DB_DIR / 'test.db').as_posix()}"
os.environ.setdefault("ENV", "test")
os.environ.setdefault("HITL_AUTO_APPROVE", "false")

import pytest  # noqa: E402

from logistics_tower.config import settings  # noqa: E402
from logistics_tower.db.seed import seed_database  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_db_environment():
    """Rebuild the canonical seed dataset (fixed RNG) before every test."""
    seed_database(force_reseed=True)
    yield


@pytest.fixture
def force_hitl(monkeypatch):
    """Make any non-empty load an 'overload' so the graph deterministically pauses at the HITL gate."""
    monkeypatch.setattr(settings, "max_weight_threshold_percent", 0.5)
    yield


@pytest.fixture(scope="session")
def google_maps_configured() -> bool:
    return settings.google_maps_api_key is not None and bool(settings.google_maps_api_key.get_secret_value())
