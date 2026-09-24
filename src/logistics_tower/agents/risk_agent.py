"""
SLA, Shift & Risk Analysis Specialist Agent.
Audits capacity, delivery windows, driver shift and cargo value of the generated plan
and decides whether the Human-in-the-Loop gate must pause execution.
"""

import logging
from typing import Any

from logistics_tower.config import settings
from logistics_tower.db.order_factory import HIGH_VALUE_CARGO_BRL
from logistics_tower.state import LogisticsAgentState, RiskWarning

logger = logging.getLogger(__name__)


def risk_agent_node(state: LogisticsAgentState) -> dict[str, Any]:
    """
    Audits:
    1. Overweight / overcube (> configured thresholds)            -> CRITICAL, HITL
    2. Missed delivery windows                                     -> CRITICAL, HITL
    3. Driver shift above the legal limit                          -> CRITICAL, HITL
    4. Orders that could not be allocated to any vehicle today     -> WARNING,  HITL
    5. High-value cargo (declared value above threshold)           -> INFO
    """
    loads = state.get("load_allocation", [])
    routes = state.get("routes", [])
    unallocated = state.get("unallocated_orders", []) or []

    warnings: list[RiskWarning] = []
    reasons: list[str] = []

    def flag(level: str, category: str, entity_id: str, description: str, reason: str | None = None) -> None:
        warnings.append({"level": level, "category": category, "entity_id": entity_id, "description": description})
        if reason:
            reasons.append(reason)

    # 1. Capacity
    for load in loads:
        v_id = load["vehicle_id"]
        w_pct, v_pct = load["weight_utilization_pct"], load["volume_utilization_pct"]
        if w_pct > settings.max_weight_threshold_percent:
            flag(
                "CRITICAL",
                "OVERLOAD",
                v_id,
                f"Veículo {v_id} excedeu a capacidade de peso com {w_pct}% (máximo: {settings.max_weight_threshold_percent}%).",
                f"Excesso de peso: {v_id} a {w_pct}%",
            )
        if v_pct > settings.max_volume_threshold_percent:
            flag(
                "CRITICAL",
                "OVERLOAD",
                v_id,
                f"Veículo {v_id} excedeu a cubagem com {v_pct}% (máximo: {settings.max_volume_threshold_percent}%).",
                f"Excesso de cubagem: {v_id} a {v_pct}%",
            )

    # 2. Time windows and 3. shift limit
    for route in routes:
        v_id = route["vehicle_id"]
        late = [s for s in route.get("stops", []) if not s.get("on_time", True)]
        for stop in late:
            flag(
                "CRITICAL",
                "SLA_BREACH",
                stop["order_id"],
                f"Janela violada em {stop['customer_name']} ({v_id}): chegada {stop['estimated_arrival']} "
                f"vs janela {stop['window_start']}-{stop['window_end']}.",
            )
        if late:
            reasons.append(f"Atraso SLA: {len(late)} parada(s) do {v_id}")
        if not route.get("within_shift_limit", True):
            flag(
                "CRITICAL",
                "SHIFT_LIMIT",
                v_id,
                f"Jornada do {v_id} ({route.get('shift_start')} ➔ {route.get('shift_end')}) excede "
                f"{settings.max_shift_hours:g}h (Lei 13.103/2015).",
                f"Jornada excedida: {v_id}",
            )

    # 4. Unallocated orders
    for order in unallocated:
        flag(
            "WARNING",
            "UNALLOCATED",
            order.get("order_id", "?"),
            f"Pedido {order.get('order_id')} ({order.get('customer_name')}, {order.get('weight_kg')} kg) "
            "não coube em nenhum veículo hoje e permanece pendente.",
        )
    if unallocated:
        reasons.append(f"{len(unallocated)} pedido(s) sem veículo")

    # 5. High-value cargo (informational)
    for load in loads:
        for order in load.get("orders", []):
            if (
                order.get("priority") == "HIGH_RISK_LOAD"
                or float(order.get("value_brl", 0) or 0) > HIGH_VALUE_CARGO_BRL
            ):
                flag(
                    "INFO",
                    "SECURITY",
                    order["order_id"],
                    f"Carga de alto valor (R$ {float(order.get('value_brl', 0) or 0):,.2f}) no veículo "
                    f"{load['vehicle_id']}. Exige rastreamento ativo.",
                )

    requires_hitl = bool(reasons)
    log_msg = f"RiskAgent: audit completed with {len(warnings)} alert(s). HITL required: {requires_hitl}"
    logger.info(log_msg)

    return {
        "risk_warnings": warnings,
        "requires_human_approval": requires_hitl,
        "human_approval_reason": "; ".join(reasons) if reasons else "Plano de rotas em conformidade.",
        "execution_log": [*state.get("execution_log", []), log_msg],
    }
