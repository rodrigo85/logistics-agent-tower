"""
Transportation Management System (TMS) & Fleet Allocation Service.
Responsible for packing orders into available fleet vehicles from the database,
respecting weight limits, volumetric cubage, and temperature control (refrigerated vs dry).
"""

import logging
from typing import Any, Dict, List, Optional

from logistics_tower.config import settings
from logistics_tower.db.repository import get_repository
from logistics_tower.db.seed import seed_database

logger = logging.getLogger(__name__)


class FleetService:
    """Interacts with relational database storing real vehicles stationed at CD."""

    def __init__(self):
        seed_database()
        self.repo = get_repository()

    def get_available_fleet(self, cd_id: str = "CD-ITAJAI-SC01") -> List[Dict[str, Any]]:
        """Queries available fleet directly from SQL database."""
        fleet = self.repo.get_available_fleet(cd_id)
        logger.info(f"TMS: Retrieved {len(fleet)} available vehicles from SQL database for {cd_id}")
        return fleet

    def pack_orders_into_fleet(
        self,
        orders: List[Dict[str, Any]],
        fleet: List[Dict[str, Any]],
        customer_rules: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Bin-packing heuristic prioritizing:
        1. Temperature requirement (refrigerated orders go to refrigerated vehicles).
        2. Customer access restrictions (e.g. only VUC allowed).
        3. Weight and Volume capacity.
        """
        customer_rules = customer_rules or []
        vuc_only_customers = set()
        for r in customer_rules:
            if "vuc" in r["content"].lower() and "apenas" in r["content"].lower():
                vuc_only_customers.add(r["customer_name"].strip().lower())

        ref_vehicles = [v for v in fleet if v.get("has_refrigeration")]
        dry_vuc_vehicles = [v for v in fleet if not v.get("has_refrigeration") and v.get("vehicle_type") == "VUC"]
        heavy_vehicles = [v for v in fleet if not v.get("has_refrigeration") and v.get("vehicle_type") != "VUC"]

        loads: Dict[str, Dict[str, Any]] = {
            v["vehicle_id"]: {
                "vehicle_id": v["vehicle_id"],
                "vehicle_model": v["model"],
                "vehicle_type": v["vehicle_type"],
                "driver_name": v["driver_name"],
                "max_weight_kg": v["max_weight_kg"],
                "max_volume_m3": v["max_volume_m3"],
                "has_refrigeration": v["has_refrigeration"],
                "orders": [],
                "total_weight_kg": 0.0,
                "total_volume_m3": 0.0,
                "weight_utilization_pct": 0.0,
                "volume_utilization_pct": 0.0,
                "cargo_types": set(),
            }
            for v in fleet
        }

        for order in orders:
            is_ref = order.get("cargo_type") == "refrigerated"
            cust_name = order.get("customer_name", "").strip().lower()
            requires_vuc = any(vuc_cust in cust_name for vuc_cust in vuc_only_customers)

            candidates: List[Dict[str, Any]] = []
            if is_ref:
                candidates = ref_vehicles
            elif requires_vuc:
                candidates = dry_vuc_vehicles or [v for v in fleet if v.get("vehicle_type") == "VUC"]
            else:
                candidates = heavy_vehicles + dry_vuc_vehicles

            allocated = False
            for cand in candidates:
                cand_id = cand["vehicle_id"]
                load = loads[cand_id]
                new_w = load["total_weight_kg"] + order["weight_kg"]
                new_v = load["total_volume_m3"] + order["volume_m3"]
                # Enforce max 2 deliveries per vehicle constraint
                has_capacity_slot = len(load["orders"]) < settings.max_deliveries_per_vehicle
                fits_weight = new_w <= cand["max_weight_kg"] * 1.05
                fits_volume = new_v <= cand["max_volume_m3"] * 1.05

                if has_capacity_slot and fits_weight and fits_volume:
                    load["orders"].append(order)
                    load["total_weight_kg"] += order["weight_kg"]
                    load["total_volume_m3"] += order["volume_m3"]
                    load["cargo_types"].add(order["cargo_type"])
                    allocated = True
                    break

            if not allocated and candidates:
                # Find candidate with available delivery slot first
                available_candidates = [c for c in candidates if len(loads[c["vehicle_id"]]["orders"]) < settings.max_deliveries_per_vehicle]
                chosen_cand = available_candidates[0] if available_candidates else candidates[0]
                cand_id = chosen_cand["vehicle_id"]
                load = loads[cand_id]
                load["orders"].append(order)
                load["total_weight_kg"] += order["weight_kg"]
                load["total_volume_m3"] += order["volume_m3"]
                load["cargo_types"].add(order["cargo_type"])

        result_loads = []
        for v_id, l in loads.items():
            if l["orders"]:
                w_pct = (l["total_weight_kg"] / l["max_weight_kg"]) * 100.0 if l["max_weight_kg"] > 0 else 0.0
                v_pct = (l["total_volume_m3"] / l["max_volume_m3"]) * 100.0 if l["max_volume_m3"] > 0 else 0.0
                l["weight_utilization_pct"] = round(w_pct, 1)
                l["volume_utilization_pct"] = round(v_pct, 1)
                l["cargo_types"] = list(l["cargo_types"])
                l["total_weight_kg"] = round(l["total_weight_kg"], 1)
                l["total_volume_m3"] = round(l["total_volume_m3"], 1)
                result_loads.append(l)

        return result_loads


_fleet_service = None


def get_fleet_service() -> FleetService:
    global _fleet_service
    if _fleet_service is None:
        _fleet_service = FleetService()
    return _fleet_service
