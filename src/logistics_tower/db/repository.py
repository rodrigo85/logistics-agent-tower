"""
Repository layer: the only module that talks SQLAlchemy.

Serves the WMS/TMS services, the long-term memory and the copilot tools with plain
dicts (the graph state must stay JSON-serialisable). Orders are always scoped by
delivery date; `None` means "today".
"""

import difflib
import hashlib
import json
import random
import unicodedata
from collections.abc import Mapping
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import joinedload

from logistics_tower.config import settings
from logistics_tower.dates import parse_delivery_date, planning_days, today
from logistics_tower.db.models import Customer, CustomerRule, DispatchManifest, OperatorMemory, Order, Vehicle
from logistics_tower.db.order_factory import build_orders_for_days
from logistics_tower.db.session import SessionLocal, init_db

_DEFAULT_CD = settings.default_cd_id
ACTIVE_STATUSES = ("PENDING", "DISPATCHED")  # part of a day's plan (DISPATCHED = approved plan)


def _stable_digits(text: str, length: int) -> str:
    """Deterministic numeric fingerprint (Python's `hash()` is salted per process)."""
    digest = hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()
    return str(int(digest, 16) % (10**length)).zfill(length)


def normalize_text(text: str) -> str:
    """Lower-case, accent-free, single-spaced text for fuzzy customer matching."""
    stripped = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))
    return " ".join(stripped.lower().replace("-", " ").split())


def _as_date(value: str | date | None) -> date:
    return parse_delivery_date(value) if not isinstance(value, date) else value


def _customer_to_dict(c: Customer) -> dict[str, Any]:
    return {
        "customer_id": c.id,
        "customer_code": c.code,
        "customer_name": c.name,
        "segment": c.segment,
        "city": c.city,
        "neighborhood": c.neighborhood,
        "address": f"{c.address} - {c.neighborhood}, {c.city} - {c.state}",
        "dock_type": c.dock_type,
        "max_vehicle_allowed": c.max_vehicle_allowed,
        "window_override": (
            f"{c.window_override_start} - {c.window_override_end}" if c.window_override_start else None
        ),
    }


def _order_to_dict(o: Order) -> dict[str, Any]:
    c = o.customer
    return {
        "order_id": o.order_number,
        "customer_id": c.id,
        "customer_code": c.code,
        "customer_name": c.name,
        "segment": c.segment,
        "city": c.city,
        "dock_type": c.dock_type,
        "max_vehicle_allowed": c.max_vehicle_allowed,
        "address": f"{c.address} - {c.neighborhood}, {c.city} - {c.state}",
        "lat": c.lat,
        "lng": c.lng,
        "delivery_date": o.delivery_date.isoformat(),
        "weight_kg": o.weight_kg,
        "volume_m3": o.volume_m3,
        "cargo_type": o.cargo_type,
        "temperature_regime": o.temperature_regime,
        "window_start": o.window_start,
        "window_end": o.window_end,
        "priority": o.priority,
        "value_brl": o.value_brl,
        "status": o.status,
        "skip_reason": o.skip_reason,
    }


def _vehicle_to_dict(v: Vehicle) -> dict[str, Any]:
    return {
        "vehicle_id": v.vehicle_id,
        "plate": v.plate,
        "model": v.model,
        "vehicle_type": v.vehicle_type,
        "max_weight_kg": v.max_weight_kg,
        "max_volume_m3": v.max_volume_m3,
        "has_refrigeration": v.has_refrigeration,
        "driver_name": v.driver_name,
        "driver_phone": v.driver_phone,
        "current_status": v.current_status,
    }


def _rule_to_dict(r: CustomerRule) -> dict[str, Any]:
    return {
        "customer_name": r.customer.name,
        "customer_code": r.customer.code,
        "max_vehicle_allowed": r.customer.max_vehicle_allowed,
        "rule_category": r.rule_category,
        "content": r.content,
        "effective_priority": r.priority,
    }


def _customer_for_factory(c: Customer) -> dict[str, Any]:
    return {
        "id": c.id,
        "segment": c.segment,
        "name": c.name,
        "window_override_start": c.window_override_start,
        "window_override_end": c.window_override_end,
    }


class LogisticsRepository:
    """Data-access layer shared by the WMS, TMS, long-term memory and the copilot."""

    def __init__(self):
        init_db()

    # ------------------------------------------------------------- reads
    def get_pending_orders(
        self, cd_id: str = _DEFAULT_CD, delivery_date: str | date | None = None
    ) -> list[dict[str, Any]]:
        """Pending orders of one delivery date (default today) joined with customer location data."""
        day = _as_date(delivery_date)
        with SessionLocal() as session:
            orders = (
                session.query(Order)
                .options(joinedload(Order.customer))
                .filter(Order.cd_id == cd_id, Order.status == "PENDING", Order.delivery_date == day)
                .all()
            )
            return [_order_to_dict(o) for o in orders]

    def get_orders_by_status(
        self, status: str, cd_id: str = _DEFAULT_CD, delivery_date: str | date | None = None
    ) -> list[dict[str, Any]]:
        """Orders with a given status; `delivery_date="all"` returns every date in the horizon."""
        with SessionLocal() as session:
            query = (
                session.query(Order)
                .options(joinedload(Order.customer))
                .filter(Order.cd_id == cd_id, Order.status == status.upper())
            )
            if delivery_date != "all":
                query = query.filter(Order.delivery_date == _as_date(delivery_date))
            return [_order_to_dict(o) for o in query.order_by(Order.delivery_date, Order.window_start).all()]

    def get_day_summary(self, cd_id: str = _DEFAULT_CD) -> list[dict[str, Any]]:
        """Per planning day: counts by status (feeds the dashboard date tabs and the copilot prompt)."""
        with SessionLocal() as session:
            rows = []
            for day in planning_days():
                counts = {
                    st: session.query(Order)
                    .filter(Order.cd_id == cd_id, Order.delivery_date == day, Order.status == st)
                    .count()
                    for st in ("PENDING", "DISPATCHED", "SKIPPED")
                }
                rows.append({"date": day.isoformat(), **{k.lower(): v for k, v in counts.items()}})
            return rows

    def get_available_fleet(self, cd_id: str = _DEFAULT_CD) -> list[dict[str, Any]]:
        with SessionLocal() as session:
            fleet = (
                session.query(Vehicle).filter(Vehicle.home_cd_id == cd_id, Vehicle.current_status == "AVAILABLE").all()
            )
            return [_vehicle_to_dict(v) for v in fleet]

    def get_all_customer_rules(self) -> list[dict[str, Any]]:
        with SessionLocal() as session:
            rules = session.query(CustomerRule).options(joinedload(CustomerRule.customer)).all()
            return [_rule_to_dict(r) for r in rules]

    # ------------------------------------------------------------ writes
    def add_customer_rule(self, customer_name: str, rule_category: str, content: str, priority: str = "HIGH") -> None:
        with SessionLocal() as session:
            cust = session.query(Customer).filter(Customer.name.ilike(f"%{customer_name}%")).first()
            if not cust:
                cust = Customer(
                    code=f"CUST-{_stable_digits(customer_name, 4)}",
                    name=customer_name,
                    document_cnpj=_stable_digits(customer_name, 14),
                    address="Endereço não informado",
                    neighborhood="Centro",
                    city="Itajaí",
                    state="SC",
                    zip_code="88301-000",
                    lat=-26.9070,
                    lng=-48.6540,
                )
                session.add(cust)
                session.flush()
            session.add(
                CustomerRule(customer_id=cust.id, rule_category=rule_category, content=content, priority=priority)
            )
            session.commit()

    def save_dispatch_manifest(
        self,
        manifest_id: str,
        cd_id: str,
        total_orders: int,
        total_vehicles: int,
        total_weight_kg: float,
        total_volume_m3: float,
        status: str,
        human_verdict: str | None,
        human_feedback: str | None,
        manifest_dict: Mapping[str, Any],
        plan_date: str | date | None = None,
    ) -> None:
        """Persist the manifest and mark its orders DISPATCHED when approved."""
        with SessionLocal() as session:
            session.add(
                DispatchManifest(
                    manifest_id=manifest_id,
                    cd_id=cd_id,
                    plan_date=_as_date(plan_date),
                    created_at=datetime.now(timezone.utc),
                    total_orders=total_orders,
                    total_vehicles=total_vehicles,
                    total_weight_kg=total_weight_kg,
                    total_volume_m3=total_volume_m3,
                    status=status,
                    human_verdict=human_verdict,
                    human_feedback=human_feedback,
                    manifest_payload_json=json.dumps(manifest_dict, ensure_ascii=False),
                )
            )
            if status == "DISPATCHED":
                order_ids = [
                    stop["order_id"] for route in manifest_dict.get("routes", []) for stop in route.get("stops", [])
                ]
                session.query(Order).filter(Order.order_number.in_(order_ids)).update(
                    {"status": "DISPATCHED"}, synchronize_session=False
                )
            session.commit()

    def reset_orders_status(
        self, cd_id: str = _DEFAULT_CD, delivery_date: str | date | None = None, include_skipped: bool = False
    ) -> None:
        """Bring a day's DISPATCHED orders back to PENDING before re-planning (SKIPPED stay out unless asked)."""
        statuses = ["DISPATCHED", "SKIPPED"] if include_skipped else ["DISPATCHED"]
        with SessionLocal() as session:
            session.query(Order).filter(
                Order.cd_id == cd_id, Order.delivery_date == _as_date(delivery_date), Order.status.in_(statuses)
            ).update({"status": "PENDING", "skip_reason": None}, synchronize_session=False)
            session.commit()

    def generate_random_orders(
        self, cd_id: str = _DEFAULT_CD, count: int = 40, days: int | None = None
    ) -> list[dict[str, Any]]:
        """
        Replace the whole planning horizon with `count` fresh refrigerated orders per day
        (one per distinct customer, capped by the pool). Returns today's pending orders.
        """
        from logistics_tower.db.seed import sync_customers  # local import: seed depends on this module

        horizon = planning_days(days)
        with SessionLocal() as session:
            sync_customers(session)
            session.query(Order).filter(Order.cd_id == cd_id, Order.delivery_date.in_(horizon)).delete(
                synchronize_session=False
            )
            customers = [_customer_for_factory(c) for c in session.query(Customer).all()]
            for o in build_orders_for_days(customers, count, random.Random(), cd_id=cd_id, days=horizon):
                session.add(Order(**o))
            session.commit()
        return self.get_pending_orders(cd_id)

    # ------------------------------------------------------------ copilot
    def find_customers(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Fuzzy customer lookup by name / code / neighbourhood / city, with their orders in the horizon."""
        q = normalize_text(query)
        if not q:
            return []
        horizon = planning_days()
        with SessionLocal() as session:
            scored: list[tuple[float, Customer]] = []
            for c in session.query(Customer).all():
                name = normalize_text(c.name)
                haystack = f"{name} {normalize_text(c.code)} {normalize_text(c.neighborhood)} {normalize_text(c.city)}"
                if q == name or q == normalize_text(c.code):
                    score = 1.0
                elif q in haystack:
                    score = 0.9
                else:
                    tokens = [t for t in q.split() if len(t) > 2]
                    hits = sum(1 for t in tokens if t in haystack)
                    ratio = difflib.SequenceMatcher(None, q, name).ratio()
                    score = max(ratio, 0.6 + 0.1 * hits if tokens and hits == len(tokens) else 0.0)
                if score >= 0.55:
                    scored.append((score, c))
            scored.sort(key=lambda t: (-t[0], t[1].name))
            result = []
            for score, c in scored[:limit]:
                orders = (
                    session.query(Order)
                    .filter(Order.customer_id == c.id, Order.delivery_date.in_(horizon))
                    .order_by(Order.delivery_date)
                    .all()
                )
                data = _customer_to_dict(c)
                data["match_score"] = round(score, 2)
                data["orders"] = [
                    {"order_id": o.order_number, "date": o.delivery_date.isoformat(), "status": o.status}
                    for o in orders
                ]
                data["pending_orders"] = sum(1 for o in orders if o.status in ACTIVE_STATUSES)
                data["skipped_orders"] = sum(1 for o in orders if o.status == "SKIPPED")
                result.append(data)
            return result

    def _customer_orders(self, session, customer_id: int, day: date, statuses: tuple[str, ...]) -> list[Order]:
        return (
            session.query(Order)
            .filter(Order.customer_id == customer_id, Order.delivery_date == day, Order.status.in_(statuses))
            .all()
        )

    def skip_customer_orders(self, customer_id: int, reason: str, delivery_date: str | date | None = None) -> list[str]:
        """Take a customer's orders of one day out of that day's plan (kept as SKIPPED)."""
        day = _as_date(delivery_date)
        with SessionLocal() as session:
            orders = self._customer_orders(session, customer_id, day, ACTIVE_STATUSES)
            for o in orders:
                o.status = "SKIPPED"
                o.skip_reason = reason[:255]
            session.commit()
            return [o.order_number for o in orders]

    def restore_customer_orders(self, customer_id: int, delivery_date: str | date | None = None) -> list[str]:
        day = _as_date(delivery_date)
        with SessionLocal() as session:
            orders = self._customer_orders(session, customer_id, day, ("SKIPPED",))
            for o in orders:
                o.status = "PENDING"
                o.skip_reason = None
            session.commit()
            return [o.order_number for o in orders]

    def move_customer_orders(self, customer_id: int, from_date: str | date | None, to_date: str | date) -> list[str]:
        """Move a customer's orders (any status) from one delivery day to another; they become PENDING there."""
        src, dst = _as_date(from_date), _as_date(to_date)
        with SessionLocal() as session:
            orders = self._customer_orders(session, customer_id, src, ("PENDING", "DISPATCHED", "SKIPPED"))
            for o in orders:
                o.delivery_date = dst
                o.status = "PENDING"
                o.skip_reason = None
            session.commit()
            return [o.order_number for o in orders]

    def reschedule_customer_window(
        self,
        customer_id: int,
        window_start: str,
        window_end: str,
        remember: bool = True,
        delivery_date: str | date | None = None,
    ) -> list[str]:
        """Change the receiving window of a customer's orders on one day (or every day when `delivery_date="all"`)."""
        with SessionLocal() as session:
            query = session.query(Order).filter(
                Order.customer_id == customer_id, Order.status.in_(("PENDING", "DISPATCHED", "SKIPPED"))
            )
            if delivery_date != "all":
                query = query.filter(Order.delivery_date == _as_date(delivery_date))
            orders = query.all()
            for o in orders:
                o.window_start = window_start
                o.window_end = window_end
            if remember:
                cust = session.get(Customer, customer_id)
                if cust is not None:
                    cust.window_override_start = window_start
                    cust.window_override_end = window_end
            session.commit()
            return [o.order_number for o in orders]

    def add_operator_memory(self, category: str, content: str) -> None:
        with SessionLocal() as session:
            session.add(OperatorMemory(category=category, content=content[:2000]))
            session.commit()

    def get_operator_memories(self, limit: int = 20) -> list[dict[str, Any]]:
        with SessionLocal() as session:
            rows = (
                session.query(OperatorMemory)
                .order_by(OperatorMemory.created_at.desc(), OperatorMemory.id.desc())
                .limit(limit)
                .all()
            )
            return [
                {"id": r.id, "category": r.category, "content": r.content, "created_at": r.created_at.isoformat()}
                for r in rows
            ]


_repo: LogisticsRepository | None = None


def get_repository() -> LogisticsRepository:
    global _repo
    if _repo is None:
        _repo = LogisticsRepository()
    return _repo


__all__ = ["ACTIVE_STATUSES", "LogisticsRepository", "get_repository", "normalize_text", "today"]
