"""
Repository Layer for Database Queries.
Connects WMS, TMS, and Memory services directly to relational database tables.
"""

import hashlib
import json
import random
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import joinedload

from logistics_tower.config import settings
from logistics_tower.db.models import Customer, CustomerRule, DispatchManifest, Order, Vehicle
from logistics_tower.db.order_factory import build_orders
from logistics_tower.db.session import SessionLocal, init_db

_DEFAULT_CD = settings.default_cd_id


def _stable_digits(text: str, length: int) -> str:
    """Deterministic numeric fingerprint (Python's `hash()` is salted per process)."""
    digest = hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()
    return str(int(digest, 16) % (10**length)).zfill(length)


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
        "weight_kg": o.weight_kg,
        "volume_m3": o.volume_m3,
        "cargo_type": o.cargo_type,
        "temperature_regime": o.temperature_regime,
        "window_start": o.window_start,
        "window_end": o.window_end,
        "priority": o.priority,
        "value_brl": o.value_brl,
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


class LogisticsRepository:
    """Data-access layer shared by the WMS, TMS and long-term memory services."""

    def __init__(self):
        init_db()

    def get_pending_orders(self, cd_id: str = _DEFAULT_CD) -> list[dict[str, Any]]:
        """Queries pending orders from the database joined with customer location data."""
        with SessionLocal() as session:
            orders = (
                session.query(Order)
                .options(joinedload(Order.customer))
                .filter(Order.cd_id == cd_id, Order.status == "PENDING")
                .all()
            )

            return [_order_to_dict(o) for o in orders]

    def get_available_fleet(self, cd_id: str = _DEFAULT_CD) -> list[dict[str, Any]]:
        """Queries available fleet from the database."""
        with SessionLocal() as session:
            fleet = (
                session.query(Vehicle).filter(Vehicle.home_cd_id == cd_id, Vehicle.current_status == "AVAILABLE").all()
            )

            return [_vehicle_to_dict(v) for v in fleet]

    def get_all_customer_rules(self) -> list[dict[str, Any]]:
        """Queries all active customer dock and operational rules."""
        with SessionLocal() as session:
            rules = session.query(CustomerRule).options(joinedload(CustomerRule.customer)).all()
            return [_rule_to_dict(r) for r in rules]

    def add_customer_rule(self, customer_name: str, rule_category: str, content: str, priority: str = "HIGH") -> None:
        """Inserts a new rule into database for a customer."""
        with SessionLocal() as session:
            cust = session.query(Customer).filter(Customer.name.ilike(f"%{customer_name}%")).first()
            if not cust:
                # Create customer if doesn't exist
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

            rule = CustomerRule(
                customer_id=cust.id,
                rule_category=rule_category,
                content=content,
                priority=priority,
            )
            session.add(rule)
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
    ) -> None:
        """Persists the final dispatch manifest and updates order statuses."""
        with SessionLocal() as session:
            manifest = DispatchManifest(
                manifest_id=manifest_id,
                cd_id=cd_id,
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
            session.add(manifest)

            # If dispatched, update order status to ALLOCATED / DISPATCHED
            if status == "DISPATCHED":
                order_ids = [
                    stop["order_id"] for route in manifest_dict.get("routes", []) for stop in route.get("stops", [])
                ]

                session.query(Order).filter(Order.order_number.in_(order_ids)).update(
                    {"status": "DISPATCHED"}, synchronize_session=False
                )

            session.commit()

    def reset_orders_status(self, cd_id: str = _DEFAULT_CD) -> None:
        """Resets all orders back to PENDING for test isolation or fresh shift planning."""
        with SessionLocal() as session:
            session.query(Order).filter(Order.cd_id == cd_id).update({"status": "PENDING"}, synchronize_session=False)
            session.commit()

    def generate_random_orders(self, cd_id: str = _DEFAULT_CD, count: int = 40) -> list[dict[str, Any]]:
        """
        Replace the pending order set with `count` fresh refrigerated orders, one per
        distinct customer of the regional pool (capped by the pool size).
        """
        from logistics_tower.db.seed import sync_customers  # local import: seed depends on this module

        with SessionLocal() as session:
            sync_customers(session)
            session.query(Order).filter(Order.cd_id == cd_id, Order.status == "PENDING").delete(
                synchronize_session=False
            )
            customers = [{"id": c.id, "segment": c.segment, "name": c.name} for c in session.query(Customer).all()]
            for o in build_orders(customers, count, random.Random(), cd_id=cd_id):
                session.add(Order(**o))
            session.commit()

        return self.get_pending_orders(cd_id)


_repo: LogisticsRepository | None = None


def get_repository() -> LogisticsRepository:
    global _repo
    if _repo is None:
        _repo = LogisticsRepository()
    return _repo
