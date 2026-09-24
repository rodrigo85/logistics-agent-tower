"""Order generation endpoints (WMS simulation)."""

from fastapi import APIRouter, Query

from logistics_tower.api.dependencies import get_plan_cache
from logistics_tower.api.schemas import GenerateOrdersResponse
from logistics_tower.config import settings
from logistics_tower.db.repository import get_repository

router = APIRouter(prefix="/api/orders", tags=["Orders"])


@router.post("/generate", response_model=GenerateOrdersResponse)
def generate_orders(count: int = Query(default=40, ge=1, le=120)) -> GenerateOrdersResponse:
    """
    Replaces pending orders with `count` refrigerated orders (one per customer) for
    supermarkets, grocery stores, bakeries, butchers and similar retailers across
    Itajaí, Balneário Camboriú, Camboriú, Navegantes, Penha, Piçarras and Brusque.
    The pool has 56 customers, so `count` is capped at that size.
    """
    orders = get_repository().generate_random_orders(cd_id=settings.default_cd_id, count=count)
    get_plan_cache().clear()
    return GenerateOrdersResponse(
        status="ok",
        message=f"{len(orders)} novos pedidos gerados com sucesso na região.",
        count=len(orders),
        orders=orders,
    )
