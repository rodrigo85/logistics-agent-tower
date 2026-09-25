"""API routers grouped by bounded context."""

from logistics_tower.api.routers import copilot, dashboard, dispatch, fleet, orders, system, traffic

__all__ = ["copilot", "dashboard", "dispatch", "fleet", "orders", "system", "traffic"]
