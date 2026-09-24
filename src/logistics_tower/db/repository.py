"""
Repository Layer for Database Queries.
Connects WMS, TMS, and Memory services directly to relational database tables.
"""

from datetime import datetime
import json
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import joinedload

from logistics_tower.db.models import Customer, CustomerRule, DispatchManifest, Order, Vehicle
from logistics_tower.db.session import SessionLocal, init_db


class LogisticsRepository:
    def __init__(self):
        init_db()

    def get_pending_orders(self, cd_id: str = "CD-ITAJAI-SC01") -> List[Dict[str, Any]]:
        """Queries pending orders from the database joined with customer location data."""
        with SessionLocal() as session:
            orders = (
                session.query(Order)
                .options(joinedload(Order.customer))
                .filter(Order.cd_id == cd_id, Order.status == "PENDING")
                .all()
            )

            result = []
            for o in orders:
                c = o.customer
                result.append(
                    {
                        "order_id": o.order_number,
                        "customer_id": c.id,
                        "customer_code": c.code,
                        "customer_name": c.name,
                        "address": f"{c.address} - {c.neighborhood}, {c.city} - {c.state}",
                        "lat": c.lat,
                        "lng": c.lng,
                        "weight_kg": o.weight_kg,
                        "volume_m3": o.volume_m3,
                        "cargo_type": o.cargo_type,
                        "window_start": o.window_start,
                        "window_end": o.window_end,
                        "priority": o.priority,
                        "value_brl": o.value_brl,
                    }
                )
            return result

    def get_available_fleet(self, cd_id: str = "CD-ITAJAI-SC01") -> List[Dict[str, Any]]:
        """Queries available fleet from the database."""
        with SessionLocal() as session:
            fleet = (
                session.query(Vehicle)
                .filter(Vehicle.home_cd_id == cd_id, Vehicle.current_status == "AVAILABLE")
                .all()
            )

            result = []
            for v in fleet:
                result.append(
                    {
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
                )
            return result

    def get_all_customer_rules(self) -> List[Dict[str, Any]]:
        """Queries all active customer dock and operational rules."""
        with SessionLocal() as session:
            rules = session.query(CustomerRule).options(joinedload(CustomerRule.customer)).all()
            result = []
            for r in rules:
                result.append(
                    {
                        "customer_name": r.customer.name,
                        "customer_code": r.customer.code,
                        "rule_category": r.rule_category,
                        "content": r.content,
                        "effective_priority": r.priority,
                    }
                )
            return result

    def add_customer_rule(self, customer_name: str, rule_category: str, content: str, priority: str = "HIGH") -> None:
        """Inserts a new rule into database for a customer."""
        with SessionLocal() as session:
            cust = session.query(Customer).filter(Customer.name.ilike(f"%{customer_name}%")).first()
            if not cust:
                # Create customer if doesn't exist
                cust = Customer(
                    code=f"CUST-{abs(hash(customer_name)) % 10000:04d}",
                    name=customer_name,
                    document_cnpj=f"{abs(hash(customer_name)) % 100000000000000:014d}",
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
        human_verdict: Optional[str],
        human_feedback: Optional[str],
        manifest_dict: Dict[str, Any],
    ) -> None:
        """Persists the final dispatch manifest and updates order statuses."""
        with SessionLocal() as session:
            manifest = DispatchManifest(
                manifest_id=manifest_id,
                cd_id=cd_id,
                created_at=datetime.utcnow(),
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
                order_ids = []
                for r in manifest_dict.get("routes", []):
                    for s in r.get("stops", []):
                        order_ids.append(s["order_id"])

                session.query(Order).filter(Order.order_number.in_(order_ids)).update(
                    {"status": "DISPATCHED"}, synchronize_session=False
                )

            session.commit()

    def reset_orders_status(self, cd_id: str = "CD-ITAJAI-SC01") -> None:
        """Resets all orders back to PENDING for test isolation or fresh shift planning."""
        with SessionLocal() as session:
            session.query(Order).filter(Order.cd_id == cd_id).update(
                {"status": "PENDING"}, synchronize_session=False
            )
            session.commit()


_repo: Optional[LogisticsRepository] = None


def get_repository() -> LogisticsRepository:
    global _repo
    if _repo is None:
        _repo = LogisticsRepository()
    return _repo
