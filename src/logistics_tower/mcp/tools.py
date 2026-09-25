"""
Logistics tools exposed through the Model Context Protocol (MCP).

Every function here is registered twice: in-process for the LangGraph agents
(`mcp/client.py`) and over stdio for external MCP clients (`mcp/server.py`).
The conversational copilot binds the operator-facing ones as LangChain tools.

Dates: every operator tool takes a `date` argument written the way the dispatcher
says it ("hoje", "amanhã", "quinta", "26/09", "2026-09-26"); empty means today.
"""

import contextvars
import re
from typing import Any

from logistics_tower.config import settings
from logistics_tower.dates import label_for, parse_delivery_date
from logistics_tower.db.repository import get_repository, normalize_text
from logistics_tower.memory.long_term import get_customer_memory_store
from logistics_tower.services.fleet_service import get_fleet_service
from logistics_tower.services.routing_service import get_routing_service
from logistics_tower.services.wms_service import get_wms_service

# The operator's full sentence, set by the copilot for the duration of one chat turn. Lets the tools
# disambiguate a shortened customer name ("Angeloni") with the rest of the sentence ("... do Centro de Itajaí").
operator_message: contextvars.ContextVar[str] = contextvars.ContextVar("operator_message", default="")

_TIME_RE = re.compile(r"^\s*(\d{1,2})(?:[:h](\d{2})?)?\s*(?:h|hs|horas)?\s*$", re.IGNORECASE)
_EVERY_DAY = {"todos", "todas", "all", "sempre", "todos os dias"}


def normalize_clock(value: str) -> str:
    """Accept '8', '8h', '8:30', '08h30', '14 horas' and return 'HH:MM'."""
    m = _TIME_RE.match(str(value))
    if not m:
        raise ValueError(f"Horário inválido: {value!r} (use HH:MM)")
    hours, minutes = int(m.group(1)), int(m.group(2) or 0)
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        raise ValueError(f"Horário fora do intervalo: {value!r}")
    return f"{hours:02d}:{minutes:02d}"


def _day(value: str | None) -> dict[str, Any]:
    """Parse an operator date and describe it; raises ValueError on garbage."""
    d = parse_delivery_date(value or None)
    return {"date": d, "iso": d.isoformat(), "label": label_for(d)}


# ------------------------------------------------------------------ planning
def tool_get_pending_orders(cd_id: str, delivery_date: str | None = None) -> list[dict[str, Any]]:
    """Fetches the delivery orders waiting at the CD for one delivery date (default today)."""
    return get_wms_service().get_pending_orders(cd_id, delivery_date=delivery_date)


def tool_get_available_fleet(cd_id: str) -> list[dict[str, Any]]:
    """Lists all available vehicles and their load/temperature capabilities at the CD."""
    return get_fleet_service().get_available_fleet(cd_id)


def tool_get_customer_dock_rules(customer_name: str) -> list[dict[str, Any]]:
    """Retrieves long-term memory rules for a customer (e.g. dock type, vehicle size, cold-chain checks)."""
    return get_customer_memory_store().get_rules_for_customer(customer_name)


def tool_optimize_route(orders: list[dict[str, Any]], start_time: str | None = None) -> dict[str, Any]:
    """Sequences a vehicle's stops (OR-Tools TSPTW), computes ETAs, distance, shift and the daily itinerary."""
    return get_routing_service().plan_route(orders, start_time_str=start_time or settings.dock_start_time)


def tool_confirm_dispatch(manifest_id: str, cd_id: str) -> dict[str, Any]:
    """Confirms final dispatch manifest in the WMS/TMS after human approval."""
    return {
        "status": "CONFIRMED",
        "manifest_id": manifest_id,
        "cd_id": cd_id,
        "message": "Ordem de carregamento e manifesto eletrônico emitidos com sucesso.",
    }


# ------------------------------------------------------- operator (copilot)
def _unique_by_score(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    best = candidates[0]
    if len(candidates) == 1:
        return best
    gap = best["match_score"] - candidates[1]["match_score"]
    if (best["match_score"] >= 0.9 and gap >= 0.1) or (best["match_score"] >= 0.8 and gap >= 0.2):
        return best
    return None


def _disambiguate_with_message(candidates: list[dict[str, Any]], message: str) -> dict[str, Any] | None:
    """Pick the candidate whose distinguishing tokens (store, neighbourhood, city) appear in the sentence."""
    if not message:
        return None
    words = set(normalize_text(message).split())
    token_sets = [
        {t for t in normalize_text(f"{c['customer_name']} {c['neighborhood']} {c['city']}").split() if len(t) > 2}
        for c in candidates
    ]
    shared = set.intersection(*token_sets) if token_sets else set()
    hits = [len((tokens - shared) & words) for tokens in token_sets]
    best = max(hits)
    if best == 0 or hits.count(best) != 1:
        return None
    return candidates[hits.index(best)]


def _resolve_customer(customer: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """
    Return (unique match, candidates). A match is unique when it clearly outranks the runner-up,
    or when the operator's full sentence singles one candidate out.
    """
    candidates = get_repository().find_customers(customer, limit=5)
    if not candidates:
        return None, []
    match = _unique_by_score(candidates) or _disambiguate_with_message(candidates, operator_message.get())
    return match, candidates


def _unresolved(customer: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "AMBIGUOUS" if candidates else "NOT_FOUND", "query": customer, "candidates": candidates}


def tool_find_customers(query: str) -> list[dict[str, Any]]:
    """Searches customers by name, code, neighbourhood or city; returns candidates with their orders per date."""
    return get_repository().find_customers(query, limit=5)


def tool_skip_customer_today(
    customer: str, reason: str = "Solicitado pelo despachante", date: str = "hoje"
) -> dict[str, Any]:
    """Removes a customer's orders of one delivery date (default today) from that day's plan; they stay as SKIPPED."""
    match, candidates = _resolve_customer(customer)
    if match is None:
        return _unresolved(customer, candidates)
    try:
        day = _day(date)
    except ValueError as exc:
        return {"status": "INVALID_DATE", "detail": str(exc)}
    repo = get_repository()
    orders = repo.skip_customer_orders(match["customer_id"], reason, delivery_date=day["date"])
    if orders:
        repo.add_operator_memory("SKIP", f"{match['customer_name']}: não atender em {day['label']} ({reason}).")
    return {
        "status": "OK" if orders else "NO_ORDERS_ON_DATE",
        "customer": match["customer_name"],
        "delivery_date": day["iso"],
        "date_label": day["label"],
        "skipped_orders": orders,
        "reason": reason,
        "customer_orders": match["orders"],
    }


def tool_restore_customer_today(customer: str, date: str = "hoje") -> dict[str, Any]:
    """Puts a customer's previously skipped orders of one delivery date (default today) back into the plan."""
    match, candidates = _resolve_customer(customer)
    if match is None:
        return _unresolved(customer, candidates)
    try:
        day = _day(date)
    except ValueError as exc:
        return {"status": "INVALID_DATE", "detail": str(exc)}
    orders = get_repository().restore_customer_orders(match["customer_id"], delivery_date=day["date"])
    return {
        "status": "OK" if orders else "NOTHING_TO_RESTORE",
        "customer": match["customer_name"],
        "delivery_date": day["iso"],
        "date_label": day["label"],
        "orders": orders,
        "customer_orders": match["orders"],
    }


def tool_move_customer_orders(customer: str, to_date: str, from_date: str = "hoje") -> dict[str, Any]:
    """Moves a customer's orders from one delivery date (default today) to another ("amanhã", "quinta", "27/09")."""
    match, candidates = _resolve_customer(customer)
    if match is None:
        return _unresolved(customer, candidates)
    try:
        src, dst = _day(from_date), _day(to_date)
    except ValueError as exc:
        return {"status": "INVALID_DATE", "detail": str(exc)}
    if src["date"] == dst["date"]:
        return {"status": "SAME_DATE", "customer": match["customer_name"], "delivery_date": src["iso"]}
    repo = get_repository()
    orders = repo.move_customer_orders(match["customer_id"], src["date"], dst["date"])
    if orders:
        repo.add_operator_memory(
            "MOVE", f"{match['customer_name']}: entrega movida de {src['label']} para {dst['label']}."
        )
    return {
        "status": "OK" if orders else "NO_ORDERS_ON_DATE",
        "customer": match["customer_name"],
        "from_date": src["iso"],
        "to_date": dst["iso"],
        "from_label": src["label"],
        "to_label": dst["label"],
        "orders": orders,
        "customer_orders": match["orders"],
    }


def tool_reschedule_customer_window(
    customer: str, window_start: str, window_end: str, remember: bool = True, date: str = "hoje"
) -> dict[str, Any]:
    """
    Sets the receiving window (HH:MM-HH:MM) of a customer's orders on one delivery date (default today;
    "todos" = every date). `remember` keeps the window for the customer's future orders.
    """
    match, candidates = _resolve_customer(customer)
    if match is None:
        return _unresolved(customer, candidates)
    try:
        start, end = normalize_clock(window_start), normalize_clock(window_end)
    except ValueError as exc:
        return {"status": "INVALID_WINDOW", "detail": str(exc)}
    if start >= end:
        return {"status": "INVALID_WINDOW", "detail": f"Janela inválida: início {start} deve ser antes do fim {end}."}
    every_day = str(date).strip().lower() in _EVERY_DAY
    try:
        day = None if every_day else _day(date)
    except ValueError as exc:
        return {"status": "INVALID_DATE", "detail": str(exc)}
    repo = get_repository()
    orders = repo.reschedule_customer_window(
        match["customer_id"],
        start,
        end,
        remember=remember,
        delivery_date="all" if day is None else day["date"],
    )
    if remember:
        repo.add_operator_memory("WINDOW", f"{match['customer_name']}: recebe entre {start} e {end}.")
        repo.add_customer_rule(
            match["customer_name"], "DOCK_WINDOW", f"Recebimento agendado entre {start} e {end}.", priority="HIGH"
        )
    return {
        "status": "OK" if orders or remember else "NO_ORDERS_ON_DATE",
        "customer": match["customer_name"],
        "window": f"{start} - {end}",
        "delivery_date": "all" if day is None else day["iso"],
        "date_label": "todos os dias" if day is None else day["label"],
        "orders_updated": orders,
        "remembered": remember,
        "customer_orders": match["orders"],
    }


def tool_list_orders(status: str = "PENDING", date: str = "hoje") -> list[dict[str, Any]]:
    """Lists orders of one delivery date (default today; "todos" = whole horizon) by status: PENDING, SKIPPED, DISPATCHED."""
    every_day = str(date).strip().lower() in _EVERY_DAY
    rows = get_repository().get_orders_by_status(
        status.upper(), settings.default_cd_id, delivery_date="all" if every_day else parse_delivery_date(date)
    )
    return [
        {
            "order_id": o["order_id"],
            "customer": o["customer_name"],
            "city": o["city"],
            "delivery_date": o["delivery_date"],
            "window": f"{o['window_start']} - {o['window_end']}",
            "weight_kg": o["weight_kg"],
            "status": o["status"],
            "skip_reason": o.get("skip_reason"),
        }
        for o in rows
    ]


def tool_remember_note(note: str) -> dict[str, Any]:
    """Stores a standing instruction from the dispatcher in long-term memory."""
    get_repository().add_operator_memory("NOTE", note)
    return {"status": "OK", "note": note}
