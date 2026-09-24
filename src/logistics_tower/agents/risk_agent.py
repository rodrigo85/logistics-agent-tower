"""
SLA, Urban Restriction & Risk Analysis Specialist Agent.
Audits vehicle routes, loading capacity thresholds, and delivery windows for compliance.
Triggers Human-in-the-Loop (HITL) gate if critical exceptions occur.
"""

import logging
from typing import Any, Dict, List

from logistics_tower.config import settings
from logistics_tower.state import LogisticsAgentState, RiskWarning

logger = logging.getLogger(__name__)


def risk_agent_node(state: LogisticsAgentState) -> Dict[str, Any]:
    """
    Risk Agent:
    Audits the generated plan for:
    1. Overweight / Overcube (> settings.max_weight_threshold_percent).
    2. Late deliveries / window violations.
    3. High-value cargo security constraints.
    """
    loads = state.get("load_allocation", [])
    routes = state.get("routes", [])

    warnings: List[RiskWarning] = []
    requires_hitl = False
    reasons: List[str] = []

    # 1. Capacity audits
    for load in loads:
        v_id = load["vehicle_id"]
        w_pct = load["weight_utilization_pct"]
        v_pct = load["volume_utilization_pct"]

        if w_pct >= settings.max_weight_threshold_percent:
            warn = {
                "level": "WARNING",
                "category": "OVERLOAD",
                "entity_id": v_id,
                "description": f"Veículo {v_id} atingiu {w_pct}% da capacidade de peso (limite alerta: {settings.max_weight_threshold_percent}%).",
            }
            warnings.append(warn)
            requires_hitl = True
            reasons.append(f"Alerta de Peso Alto: {v_id} a {w_pct}%")

        if v_pct >= settings.max_volume_threshold_percent:
            warn = {
                "level": "WARNING",
                "category": "OVERLOAD",
                "entity_id": v_id,
                "description": f"Veículo {v_id} atingiu {v_pct}% da cubagem volumétrica.",
            }
            warnings.append(warn)
            requires_hitl = True
            reasons.append(f"Alerta de Cubagem: {v_id} a {v_pct}%")

    # 2. Window / SLA audits
    for route in routes:
        v_id = route["vehicle_id"]
        for stop in route["stops"]:
            if not stop["on_time"]:
                warn = {
                    "level": "CRITICAL",
                    "category": "SLA_BREACH",
                    "entity_id": stop["order_id"],
                    "description": f"Janela de entrega violada para {stop['customer_name']}: previsão {stop['estimated_arrival']} vs janela {stop['window_start']}-{stop['window_end']}.",
                }
                warnings.append(warn)
                requires_hitl = True
                reasons.append(f"Atraso SLA: {stop['customer_name']}")

    # 3. High risk cargo audit
    for load in loads:
        for order in load.get("orders", []):
            if order.get("priority") == "HIGH_RISK_LOAD" or order.get("value_brl", 0) > 50000.0:
                warnings.append(
                    {
                        "level": "INFO",
                        "category": "SECURITY",
                        "entity_id": order["order_id"],
                        "description": f"Carga de alto valor (R$ {order.get('value_brl', 0):,.2f}) alocada ao veículo {load['vehicle_id']}. Exige rastreamento ativo.",
                    }
                )

    log_msg = f"RiskAgent: Audit completed. Generated {len(warnings)} alerts. HITL required: {requires_hitl}"
    logger.info(log_msg)

    return {
        "risk_warnings": warnings,
        "requires_human_approval": requires_hitl,
        "human_approval_reason": "; ".join(reasons) if reasons else "Plano de rotas em conformidade.",
        "execution_log": state.get("execution_log", []) + [log_msg],
    }
