"""Pytest configuration and global test fixtures."""

import pytest
from logistics_tower.db.repository import get_repository
from logistics_tower.db.seed import seed_database


@pytest.fixture(autouse=True)
def isolated_db_environment():
    """Ensures database is initialized, seeded, and orders are set to PENDING before each test."""
    seed_database()
    repo = get_repository()
    repo.reset_orders_status()
    yield
