"""
Regenerate the reference fixtures under data/samples from the seed definitions.

Usage: python scripts/export_samples.py
The fixtures are documentation artefacts (they are not read by the application);
keeping them in sync with the seeder lets reviewers inspect the data model without a database.
"""

import json
import random
from pathlib import Path

from logistics_tower.config import settings
from logistics_tower.db.address_pool import REGIONAL_CUSTOMERS_POOL
from logistics_tower.db.order_factory import build_orders
from logistics_tower.db.seed import FLEET_SEED_DATA, SEED_ORDER_COUNT, SEED_ORDER_PREFIX, SEED_RNG

SAMPLES_DIR = Path(__file__).resolve().parents[1] / "data" / "samples"


def main() -> None:
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    customers = [{"id": idx + 1, **c} for idx, c in enumerate(REGIONAL_CUSTOMERS_POOL)]
    by_id = {c["id"]: c for c in customers}
    rng = random.Random(SEED_RNG)
    orders = []
    for o in build_orders(customers, SEED_ORDER_COUNT, rng, cd_id=settings.default_cd_id, prefix=SEED_ORDER_PREFIX):
        c = by_id[o["customer_id"]]
        orders.append(
            {
                "order_id": o["order_number"],
                "customer_code": c["code"],
                "customer_name": c["name"],
                "segment": c["segment"],
                "address": f"{c['address']} - {c['neighborhood']}, {c['city']} - {c['state']}",
                "lat": c["lat"],
                "lng": c["lng"],
                "weight_kg": o["weight_kg"],
                "volume_m3": o["volume_m3"],
                "cargo_type": o["cargo_type"],
                "temperature_regime": o["temperature_regime"],
                "window_start": o["window_start"],
                "window_end": o["window_end"],
                "priority": o["priority"],
                "value_brl": o["value_brl"],
            }
        )

    rules = [
        {
            "customer_code": c["code"],
            "customer_name": c["name"],
            "rule_category": r["category"],
            "content": r["content"],
            "effective_priority": r["priority"],
        }
        for c in REGIONAL_CUSTOMERS_POOL
        for r in c["rules"]
    ]

    fleet = [{k: v for k, v in vehicle.items() if k != "current_status"} for vehicle in FLEET_SEED_DATA]

    for name, payload in (("fleet.json", fleet), ("orders.json", orders), ("customer_rules.json", rules)):
        (SAMPLES_DIR / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {name}: {len(payload)} records")


if __name__ == "__main__":
    main()
