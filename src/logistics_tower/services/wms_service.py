"""
Warehouse Management System (WMS) Service.
Interface for reading pending orders from the relational database (PostgreSQL / SQLite).
"""

import logging
from typing import Any, Dict, List

from logistics_tower.db.repository import get_repository
from logistics_tower.db.seed import seed_database

logger = logging.getLogger(__name__)


class WMSService:
    """Interacts with relational database storing real customer orders."""

    def __init__(self):
        # Ensure database is initialized and seeded
        seed_database()
        self.repo = get_repository()

    def get_pending_orders(self, cd_id: str) -> List[Dict[str, Any]]:
        """Queries pending delivery orders directly from the database."""
        orders = self.repo.get_pending_orders(cd_id)
        logger.info(f"WMS: Retrieved {len(orders)} pending orders from SQL database for {cd_id}")
        return orders


_wms_service = None


def get_wms_service() -> WMSService:
    global _wms_service
    if _wms_service is None:
        _wms_service = WMSService()
    return _wms_service
