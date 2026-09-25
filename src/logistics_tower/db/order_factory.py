"""
Order factory for the cold-chain operation.

Produces realistic refrigerated orders per customer segment (weight, volume,
temperature regime, delivery window, priority and declared value). Used by the
idempotent seeder (fixed RNG) and by the "generate orders" endpoint (fresh RNG).
"""

import random
from datetime import date, datetime, timezone
from typing import Any

from logistics_tower.db.address_pool import (
    ACOUGUE,
    ATACADO,
    CONVENIENCIA,
    HORTIFRUTI,
    MERCEARIA,
    MINIMERCADO,
    PADARIA,
    PEIXARIA,
    SORVETERIA,
    SUPERMERCADO,
)

RESFRIADO = "RESFRIADO"  # 0 to 4 °C
CONGELADO = "CONGELADO"  # -18 °C

# Declared value above which the Risk Agent raises a security alert.
HIGH_VALUE_CARGO_BRL = 50_000.0

# segment -> (weight range kg, volume range m3, value per kg BRL, time windows, VIP probability)
_PROFILES: dict[str, dict[str, Any]] = {
    ATACADO: {
        "weight": (600.0, 1500.0),
        "volume": (3.0, 8.0),
        "value_per_kg": (28.0, 45.0),
        "windows": [("06:00", "11:00"), ("07:00", "12:00"), ("06:30", "10:30")],
        "vip": 0.35,
    },
    SUPERMERCADO: {
        "weight": (300.0, 900.0),
        "volume": (1.5, 5.0),
        "value_per_kg": (30.0, 60.0),
        "windows": [("06:00", "10:00"), ("07:00", "12:00"), ("08:00", "14:00"), ("06:00", "16:00")],
        "vip": 0.30,
    },
    MERCEARIA: {
        "weight": (80.0, 300.0),
        "volume": (0.4, 1.8),
        "value_per_kg": (25.0, 45.0),
        "windows": [("07:00", "12:00"), ("08:00", "16:00"), ("09:00", "17:00")],
        "vip": 0.05,
    },
    MINIMERCADO: {
        "weight": (100.0, 350.0),
        "volume": (0.5, 2.0),
        "value_per_kg": (25.0, 45.0),
        "windows": [("07:00", "12:00"), ("08:00", "16:00"), ("07:30", "15:00")],
        "vip": 0.05,
    },
    PADARIA: {
        "weight": (60.0, 200.0),
        "volume": (0.3, 1.2),
        "value_per_kg": (20.0, 35.0),
        "windows": [("05:30", "08:30"), ("06:00", "09:00")],
        "vip": 0.10,
    },
    ACOUGUE: {
        "weight": (150.0, 500.0),
        "volume": (0.8, 2.5),
        "value_per_kg": (40.0, 70.0),
        "windows": [("06:00", "10:00"), ("07:00", "11:00"), ("06:30", "12:00")],
        "vip": 0.15,
    },
    PEIXARIA: {
        "weight": (120.0, 400.0),
        "volume": (0.6, 2.0),
        "value_per_kg": (45.0, 80.0),
        "windows": [("05:30", "09:00"), ("06:00", "10:00")],
        "vip": 0.20,
    },
    HORTIFRUTI: {
        "weight": (200.0, 600.0),
        "volume": (1.2, 3.5),
        "value_per_kg": (12.0, 25.0),
        "windows": [("06:00", "09:00"), ("06:00", "11:00")],
        "vip": 0.10,
    },
    CONVENIENCIA: {
        "weight": (40.0, 150.0),
        "volume": (0.2, 0.9),
        "value_per_kg": (30.0, 50.0),
        "windows": [("08:00", "16:00"), ("09:00", "17:00")],
        "vip": 0.05,
    },
    SORVETERIA: {
        "weight": (50.0, 180.0),
        "volume": (0.3, 1.2),
        "value_per_kg": (35.0, 55.0),
        "windows": [("08:00", "14:00"), ("09:00", "16:00")],
        "vip": 0.05,
    },
}

_FROZEN_SEGMENTS = {SORVETERIA}
_FROZEN_PROBABILITY = {PEIXARIA: 0.6, ACOUGUE: 0.4, SUPERMERCADO: 0.3, ATACADO: 0.3}


def build_order(
    customer: dict[str, Any], order_number: str, rng: random.Random, cd_id: str, delivery_date: date
) -> dict[str, Any]:
    """Create one refrigerated order for a customer dict with at least `segment` and `id`."""
    segment = customer.get("segment") or SUPERMERCADO
    profile = _PROFILES.get(segment, _PROFILES[SUPERMERCADO])

    weight = round(rng.uniform(*profile["weight"]), 1)
    volume = round(rng.uniform(*profile["volume"]), 2)
    value = round(weight * rng.uniform(*profile["value_per_kg"]), 2)
    if customer.get("window_override_start") and customer.get("window_override_end"):
        window_start, window_end = customer["window_override_start"], customer["window_override_end"]
    else:
        window_start, window_end = rng.choice(profile["windows"])

    if segment in _FROZEN_SEGMENTS or rng.random() < _FROZEN_PROBABILITY.get(segment, 0.0):
        regime = CONGELADO
    else:
        regime = RESFRIADO

    if value > HIGH_VALUE_CARGO_BRL:
        priority = "HIGH_RISK_LOAD"
    elif rng.random() < profile["vip"]:
        priority = "VIP"
    else:
        priority = "STANDARD"

    return {
        "order_number": order_number,
        "customer_id": customer["id"],
        "cd_id": cd_id,
        "delivery_date": delivery_date,
        "weight_kg": weight,
        "volume_m3": volume,
        "cargo_type": "refrigerated",
        "temperature_regime": regime,
        "window_start": window_start,
        "window_end": window_end,
        "priority": priority,
        "value_brl": value,
        "status": "PENDING",
    }


def build_orders(
    customers: list[dict[str, Any]],
    count: int,
    rng: random.Random,
    cd_id: str,
    prefix: str | None = None,
    delivery_date: date | None = None,
) -> list[dict[str, Any]]:
    """
    One order per distinct customer, up to `count` (capped by the customer pool), for one delivery date.
    Customers are sampled without replacement so every stop is a different address.
    """
    if not customers or count <= 0:
        return []
    chosen = rng.sample(customers, min(count, len(customers)))
    stamp = prefix or datetime.now(timezone.utc).strftime("%m%d%H%M")
    day = delivery_date or date.today()
    return [
        build_order(c, f"ORD-ITJ-{stamp}-{day.strftime('%d%m')}-{i + 1:03d}", rng, cd_id, day)
        for i, c in enumerate(chosen)
    ]


def build_orders_for_days(
    customers: list[dict[str, Any]],
    count_per_day: int,
    rng: random.Random,
    cd_id: str,
    days: list[date],
    prefix: str | None = None,
) -> list[dict[str, Any]]:
    """`count_per_day` orders for each date in `days` (each day samples its own customers)."""
    orders: list[dict[str, Any]] = []
    for day in days:
        orders.extend(build_orders(customers, count_per_day, rng, cd_id, prefix=prefix, delivery_date=day))
    return orders
