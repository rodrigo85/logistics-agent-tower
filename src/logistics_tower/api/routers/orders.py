"""Order generation endpoints (WMS simulation)."""

from fastapi import APIRouter, Query

from logistics_tower.api.dependencies import get_dispatch_planner
from logistics_tower.api.schemas import GenerateOrdersResponse
from logistics_tower.config import settings
from logistics_tower.db.repository import get_repository

router = APIRouter(prefix="/api/orders", tags=["Orders"])


@router.post("/generate", response_model=GenerateOrdersResponse)
def generate_orders(
    count: int = Query(default=40, ge=1, le=120, description="orders per day"),
    days: int = Query(default=settings.planning_horizon_days, ge=1, le=7, description="consecutive days from today"),
) -> GenerateOrdersResponse:
    """
    Replaces the planning horizon with `count` refrigerated orders per day for `days`
    consecutive days starting today (one order per customer per day, capped by the
    56-customer pool). Returns today's pending orders and the per-day summary.
    """
    planner = get_dispatch_planner()
    orders = get_repository().generate_random_orders(cd_id=settings.default_cd_id, count=count, days=days)
    planner.clear_all()
    horizon = planner.horizon()
    total = sum(row["pending"] for row in horizon)
    return GenerateOrdersResponse(
        status="ok",
        message=f"{total} pedidos gerados para {days} dia(s) a partir de hoje ({len(orders)} para hoje).",
        count=len(orders),
        days=days,
        orders=orders,
        horizon=horizon,
    )
