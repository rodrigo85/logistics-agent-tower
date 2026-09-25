"""
Idempotent database seeder for the cold-chain operation of CD Itajaí.

Converges the schema, the five refrigerated trucks and the regional customer pool
on every call. Orders are (re)generated from a fixed random seed only when the
pending set is missing or inconsistent, or when `force_reseed=True`.
"""

import logging
import random
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from logistics_tower.config import settings
from logistics_tower.dates import planning_days, today
from logistics_tower.db.address_pool import REGIONAL_CUSTOMERS_POOL
from logistics_tower.db.models import Base, Customer, CustomerRule, Order, Vehicle
from logistics_tower.db.order_factory import build_orders_for_days
from logistics_tower.db.session import SessionLocal, engine, init_db

logger = logging.getLogger(__name__)

SEED_ORDER_COUNT = 40  # per delivery day
SEED_RNG = 2026
SEED_ORDER_PREFIX = "2026"

# Five refrigerated trucks (cold chain: 0-4 °C chilled / -18 °C frozen)
FLEET_SEED_DATA: list[dict[str, Any]] = [
    {
        "vehicle_id": "VEH-ITJ-VUC-01",
        "plate": "RLS7B14",
        "model": "Iveco Daily 35S14 Baú Frigorífico (VUC)",
        "vehicle_type": "VUC",
        "max_weight_kg": 1600.0,
        "max_volume_m3": 11.0,
        "has_refrigeration": True,
        "driver_name": "Carlos Eduardo da Silva",
        "driver_phone": "(47) 99123-4567",
        "current_status": "AVAILABLE",
        "home_cd_id": settings.default_cd_id,
    },
    {
        "vehicle_id": "VEH-ITJ-VUC-02",
        "plate": "MKB2D55",
        "model": "Mercedes-Benz Accelo 815 Baú Frigorífico (VUC)",
        "vehicle_type": "VUC",
        "max_weight_kg": 2800.0,
        "max_volume_m3": 18.0,
        "has_refrigeration": True,
        "driver_name": "Lucas Pereira de Souza",
        "driver_phone": "(47) 99456-7890",
        "current_status": "AVAILABLE",
        "home_cd_id": settings.default_cd_id,
    },
    {
        "vehicle_id": "VEH-ITJ-TOCO-03",
        "plate": "QJQ4E88",
        "model": "Mercedes-Benz Atego 1419 Baú Frigorífico (Toco)",
        "vehicle_type": "TOCO",
        "max_weight_kg": 6000.0,
        "max_volume_m3": 32.0,
        "has_refrigeration": True,
        "driver_name": "Roberto Almeida",
        "driver_phone": "(47) 99345-6789",
        "current_status": "AVAILABLE",
        "home_cd_id": settings.default_cd_id,
    },
    {
        "vehicle_id": "VEH-ITJ-TOCO-04",
        "plate": "QHP1G44",
        "model": "Volkswagen Delivery 11.180 Baú Frigorífico (Toco)",
        "vehicle_type": "TOCO",
        "max_weight_kg": 5500.0,
        "max_volume_m3": 28.0,
        "has_refrigeration": True,
        "driver_name": "André Luiz Martins",
        "driver_phone": "(47) 99678-9012",
        "current_status": "AVAILABLE",
        "home_cd_id": settings.default_cd_id,
    },
    {
        "vehicle_id": "VEH-ITJ-TRUCK-05",
        "plate": "MMI8H12",
        "model": "Volvo VM 270 Baú Frigorífico 6x2 (Truck)",
        "vehicle_type": "TRUCK",
        "max_weight_kg": 13000.0,
        "max_volume_m3": 55.0,
        "has_refrigeration": True,
        "driver_name": "João Paulo Bittencourt",
        "driver_phone": "(47) 99789-0123",
        "current_status": "AVAILABLE",
        "home_cd_id": settings.default_cd_id,
    },
]


def ensure_schema() -> None:
    """
    Create tables; if an existing table lacks a column defined in the models
    (schema evolved), rebuild the local database. There is no Alembic yet (ADR-0005),
    and the database is a regenerable cache of the seed data.
    """
    init_db()
    inspector = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {c["name"] for c in inspector.get_columns(table.name)}
        missing = {c.name for c in table.columns} - existing
        if missing:
            logger.warning("Schema drift on table '%s' (missing %s); rebuilding database.", table.name, sorted(missing))
            Base.metadata.drop_all(bind=engine)
            Base.metadata.create_all(bind=engine)
            return


def _sync_fleet(db: Session) -> None:
    target_ids = {v["vehicle_id"] for v in FLEET_SEED_DATA}
    for v in db.query(Vehicle).all():
        if v.vehicle_id not in target_ids:
            logger.info("Removing vehicle %s (not part of the configured fleet)", v.vehicle_id)
            db.delete(v)
    db.flush()
    for v_data in FLEET_SEED_DATA:
        veh = db.query(Vehicle).filter(Vehicle.vehicle_id == v_data["vehicle_id"]).first()
        if veh is None:
            db.add(Vehicle(**v_data))
        else:
            for key, val in v_data.items():
                setattr(veh, key, val)
    db.commit()


def sync_customers(db: Session) -> None:
    """Insert missing pool customers (with rules) and refresh geo/dock metadata of existing ones."""
    existing = {c.code: c for c in db.query(Customer).all()}
    for pool_cust in REGIONAL_CUSTOMERS_POOL:
        data = dict(pool_cust)
        rules_data = data.pop("rules", [])
        cust = existing.get(data["code"])
        if cust is None:
            cust = Customer(**data)
            db.add(cust)
            db.flush()
            for r in rules_data:
                db.add(
                    CustomerRule(
                        customer_id=cust.id,
                        rule_category=r["category"],
                        content=r["content"],
                        priority=r.get("priority", "HIGH"),
                    )
                )
        else:
            for key in ("segment", "dock_type", "max_vehicle_allowed", "lat", "lng"):
                setattr(cust, key, data[key])
    db.commit()


def _customer_for_factory(c: Customer) -> dict[str, Any]:
    return {
        "id": c.id,
        "segment": c.segment,
        "name": c.name,
        "window_override_start": c.window_override_start,
        "window_override_end": c.window_override_end,
    }


def _orders_need_reseed(db: Session, force: bool) -> bool:
    """Reseed when forced, when today has no orders at all (dataset rolled past its dates) or when data is inconsistent."""
    if force:
        return True
    orders_today = db.query(Order).filter(Order.delivery_date == today()).count()
    non_refrigerated = db.query(Order).filter(Order.cargo_type != "refrigerated").count()
    return orders_today == 0 or non_refrigerated > 0


def _seed_orders(db: Session, cd_id: str) -> int:
    db.query(Order).delete()
    db.commit()
    customers = [_customer_for_factory(c) for c in db.query(Customer).order_by(Customer.code).all()]
    rng = random.Random(SEED_RNG)
    orders = build_orders_for_days(
        customers, SEED_ORDER_COUNT, rng, cd_id=cd_id, days=planning_days(), prefix=SEED_ORDER_PREFIX
    )
    for o in orders:
        db.add(Order(**o))
    db.commit()
    return len(orders)


def seed_database(force_reseed: bool = False) -> None:
    """Converge schema, fleet, customers and (when needed) the pending order set."""
    ensure_schema()
    db = SessionLocal()
    try:
        _sync_fleet(db)
        sync_customers(db)
        if _orders_need_reseed(db, force_reseed):
            count = _seed_orders(db, settings.default_cd_id)
            total_cust = db.query(Customer).count()
            logger.info(
                "Database seeded: %s customers, %s refrigerated trucks, %s orders over %s days from %s.",
                total_cust,
                len(FLEET_SEED_DATA),
                count,
                settings.planning_horizon_days,
                today().isoformat(),
            )
    except Exception:
        db.rollback()
        logger.exception("Failed to seed database")
        raise
    finally:
        db.close()


def main() -> None:
    """Console entry point: `logistics-tower-seed` / `python -m logistics_tower.db.seed`."""
    from logistics_tower.logging_setup import configure_logging

    configure_logging()
    seed_database(force_reseed=True)


if __name__ == "__main__":
    main()
