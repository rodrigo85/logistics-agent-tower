"""
Warehouse Management System (WMS) Service.
Interface for reading pending orders from the relational database (PostgreSQL / SQLite).
"""

import logging
from typing import Any

from logistics_tower.db.repository import get_repository

logger = logging.getLogger(__name__)


class WMSService:
    """Reads customer orders from the relational database (seeded by the application entry point)."""

    def __init__(self):
        self.repo = get_repository()

    def get_pending_orders(self, cd_id: str, delivery_date: str | None = None) -> list[dict[str, Any]]:
        """Pending orders of one delivery date (default: today)."""
        orders = self.repo.get_pending_orders(cd_id, delivery_date=delivery_date)
        logger.info(f"WMS: Retrieved {len(orders)} pending orders for {cd_id} on {delivery_date or 'today'}")
        return orders


_wms_service = None


def get_wms_service() -> WMSService:
    global _wms_service
    if _wms_service is None:
        _wms_service = WMSService()
    return _wms_service
