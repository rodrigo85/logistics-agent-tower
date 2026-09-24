"""
Transportation Management (TMS): fleet lookup and multi-drop route allocation.

Allocation model (ADR-0006): every vehicle performs **one route per day** with
multiple stops. The goal is compact routes (nearby customers travel together)
under hard constraints:

* refrigerated cargo only on refrigerated vehicles (and vice versa);
* customers with an access restriction ("apenas VUC") only on VUC vehicles;
* utilisation never exceeds 100% of weight or volume;
* at most `MAX_STOPS_PER_VEHICLE` deliveries per route.

Algorithm (cluster-first, route-second):

1. **Sweep** (Gillett & Miller) in two passes. Orders restricted to VUC are
   swept across the VUC vehicles first; the remaining orders are swept across
   the large vehicles and then into whatever VUC capacity is left. Each pass
   sorts stops by polar angle around the CD (starting after the largest angular
   gap) and fills one vehicle at a time with consecutive stops.
2. **Deferred placement:** orders the sweep could not place go to the eligible
   route whose centroid is closest.
3. **Centroid refinement:** a few k-means-style iterations move a stop to
   another eligible route when that route's centroid is clearly closer,
   compacting clusters and shortening total distance.
"""

import logging
import math
from typing import Any

from logistics_tower.config import settings
from logistics_tower.db.repository import get_repository

logger = logging.getLogger(__name__)

_VEHICLE_RANK = {"VUC": 1, "TOCO": 2, "TRUCK": 3}
_REFINE_ITERATIONS = 6
_REFINE_GAIN = 0.8  # move a stop only when the other centroid is at least 20% closer


def vuc_only_customers(customer_rules: list[dict[str, Any]]) -> set[str]:
    """Customer names (lower-case) whose rules restrict access to VUC vehicles."""
    names: set[str] = set()
    for r in customer_rules:
        content = str(r.get("content", "")).lower()
        if ("apenas" in content and "vuc" in content) or r.get("max_vehicle_allowed") == "VUC":
            names.add(str(r.get("customer_name", "")).strip().lower())
    return names


def polar_angle(lat: float, lng: float, origin_lat: float, origin_lng: float) -> float:
    """Bearing of a point around the depot in radians, in [0, 2*pi)."""
    dy = lat - origin_lat
    dx = (lng - origin_lng) * math.cos(math.radians(origin_lat))
    return math.atan2(dy, dx) % (2 * math.pi)


def _planar_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Fast equirectangular distance in km (adequate for clustering at city scale)."""
    x = math.radians(lng2 - lng1) * math.cos(math.radians((lat1 + lat2) / 2.0))
    y = math.radians(lat2 - lat1)
    return 6371.0 * math.hypot(x, y)


def _requires_vuc(order: dict[str, Any], vuc_only: set[str]) -> bool:
    return order.get("max_vehicle_allowed") == "VUC" or str(order.get("customer_name", "")).strip().lower() in vuc_only


def _order_fits_vehicle(order: dict[str, Any], vehicle: dict[str, Any], vuc_only: set[str]) -> bool:
    is_ref = order.get("cargo_type", "refrigerated") == "refrigerated"
    if is_ref != bool(vehicle.get("has_refrigeration")):
        return False
    if _requires_vuc(order, vuc_only) and vehicle.get("vehicle_type") != "VUC":
        return False
    weight_ok = float(order.get("weight_kg", 0.0)) <= float(vehicle["max_weight_kg"])
    volume_ok = float(order.get("volume_m3", 0.0)) <= float(vehicle["max_volume_m3"])
    return weight_ok and volume_ok


def _new_load(vehicle: dict[str, Any]) -> dict[str, Any]:
    return {
        "vehicle_id": vehicle["vehicle_id"],
        "plate": vehicle.get("plate", ""),
        "vehicle_model": vehicle.get("model", ""),
        "vehicle_type": vehicle.get("vehicle_type", "VUC"),
        "driver_name": vehicle.get("driver_name", "N/A"),
        "driver_phone": vehicle.get("driver_phone"),
        "max_weight_kg": float(vehicle["max_weight_kg"]),
        "max_volume_m3": float(vehicle["max_volume_m3"]),
        "has_refrigeration": bool(vehicle.get("has_refrigeration", True)),
        "orders": [],
        "total_weight_kg": 0.0,
        "total_volume_m3": 0.0,
        "weight_utilization_pct": 0.0,
        "volume_utilization_pct": 0.0,
        "cargo_types": [],
        "stops_count": 0,
        "cities": [],
    }


def _can_add(load: dict[str, Any], order: dict[str, Any], max_stops: int) -> bool:
    w = load["total_weight_kg"] + float(order.get("weight_kg", 0.0))
    v = load["total_volume_m3"] + float(order.get("volume_m3", 0.0))
    return len(load["orders"]) < max_stops and w <= load["max_weight_kg"] and v <= load["max_volume_m3"]


def _add(load: dict[str, Any], order: dict[str, Any]) -> None:
    load["orders"].append(order)
    load["total_weight_kg"] = round(load["total_weight_kg"] + float(order.get("weight_kg", 0.0)), 1)
    load["total_volume_m3"] = round(load["total_volume_m3"] + float(order.get("volume_m3", 0.0)), 2)


def _remove(load: dict[str, Any], order: dict[str, Any]) -> None:
    load["orders"].remove(order)
    load["total_weight_kg"] = round(max(0.0, load["total_weight_kg"] - float(order.get("weight_kg", 0.0))), 1)
    load["total_volume_m3"] = round(max(0.0, load["total_volume_m3"] - float(order.get("volume_m3", 0.0))), 2)


def _centroid(load: dict[str, Any]) -> tuple[float, float]:
    n = len(load["orders"])
    return (
        sum(float(o["lat"]) for o in load["orders"]) / n,
        sum(float(o["lng"]) for o in load["orders"]) / n,
    )


def _angular_order(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort by bearing around the CD, starting right after the largest angular gap."""
    if len(orders) < 2:
        return list(orders)
    angled = sorted(
        orders, key=lambda o: polar_angle(float(o["lat"]), float(o["lng"]), settings.cd_lat, settings.cd_lng)
    )
    angles = [polar_angle(float(o["lat"]), float(o["lng"]), settings.cd_lat, settings.cd_lng) for o in angled]
    gaps = [(angles[(i + 1) % len(angles)] - angles[i]) % (2 * math.pi) for i in range(len(angles))]
    start = (gaps.index(max(gaps)) + 1) % len(angled)
    return angled[start:] + angled[:start]


def _finalise(load: dict[str, Any]) -> dict[str, Any]:
    load["stops_count"] = len(load["orders"])
    load["weight_utilization_pct"] = round(min(100.0, load["total_weight_kg"] / load["max_weight_kg"] * 100.0), 1)
    load["volume_utilization_pct"] = round(min(100.0, load["total_volume_m3"] / load["max_volume_m3"] * 100.0), 1)
    load["cargo_types"] = sorted({o.get("cargo_type", "refrigerated") for o in load["orders"]})
    load["cities"] = sorted({o.get("city", "") for o in load["orders"] if o.get("city")})
    return load


class FleetService:
    """Fleet lookup plus cluster-first multi-drop allocation."""

    def __init__(self):
        self.repo = get_repository()
        self.last_unallocated: list[dict[str, Any]] = []

    def get_available_fleet(self, cd_id: str = settings.default_cd_id) -> list[dict[str, Any]]:
        fleet = self.repo.get_available_fleet(cd_id)
        logger.info(f"TMS: Retrieved {len(fleet)} available vehicles from SQL database for {cd_id}")
        return fleet

    # ----------------------------------------------------------------- steps
    @staticmethod
    def _sweep(
        orders: list[dict[str, Any]],
        vehicles: list[dict[str, Any]],
        loads: dict[str, dict[str, Any]],
        vuc_only: set[str],
        max_stops: int,
    ) -> list[dict[str, Any]]:
        """Fill `vehicles` in order with angularly consecutive orders; return what could not be placed."""
        deferred: list[dict[str, Any]] = []
        vehicle_idx = 0
        for order in _angular_order(orders):
            placed = False
            while vehicle_idx < len(vehicles):
                vehicle = vehicles[vehicle_idx]
                load = loads[vehicle["vehicle_id"]]
                if not _order_fits_vehicle(order, vehicle, vuc_only):
                    break  # legally incompatible with this vehicle -> defer, keep sweeping
                if _can_add(load, order, max_stops):
                    _add(load, order)
                    placed = True
                    break
                vehicle_idx += 1  # vehicle full: open the next one
            if not placed:
                deferred.append(order)
        return deferred

    @staticmethod
    def _place_nearest(
        order: dict[str, Any],
        loads: dict[str, dict[str, Any]],
        vehicle_by_id: dict[str, dict[str, Any]],
        vuc_only: set[str],
        max_stops: int,
    ) -> bool:
        """Put the order on the eligible route whose centroid is closest (empty routes count as far)."""
        best_id, best_km = None, float("inf")
        for v_id, load in loads.items():
            if not _order_fits_vehicle(order, vehicle_by_id[v_id], vuc_only) or not _can_add(load, order, max_stops):
                continue
            if load["orders"]:
                c_lat, c_lng = _centroid(load)
                km = _planar_km(float(order["lat"]), float(order["lng"]), c_lat, c_lng)
            else:
                km = 1e6 - float(vehicle_by_id[v_id]["max_weight_kg"])  # prefer opening the largest idle truck
            if km < best_km:
                best_id, best_km = v_id, km
        if best_id is None:
            return False
        _add(loads[best_id], order)
        return True

    @staticmethod
    def _refine(
        loads: dict[str, dict[str, Any]],
        vehicle_by_id: dict[str, dict[str, Any]],
        vuc_only: set[str],
        max_stops: int,
    ) -> int:
        """K-means-style relocation of stops towards clearly closer route centroids."""
        moves = 0
        for _ in range(_REFINE_ITERATIONS):
            centroids = {v_id: _centroid(load) for v_id, load in loads.items() if load["orders"]}
            moved = False
            for v_id, load in loads.items():
                if len(load["orders"]) < 2:
                    continue
                for order in list(load["orders"]):
                    lat, lng = float(order["lat"]), float(order["lng"])
                    current_km = _planar_km(lat, lng, *centroids[v_id])
                    best_id, best_km = None, current_km * _REFINE_GAIN
                    for other_id, other in loads.items():
                        if other_id == v_id or not other["orders"]:
                            continue
                        if not _order_fits_vehicle(order, vehicle_by_id[other_id], vuc_only):
                            continue
                        if not _can_add(other, order, max_stops):
                            continue
                        km = _planar_km(lat, lng, *centroids[other_id])
                        if km < best_km:
                            best_id, best_km = other_id, km
                    if best_id is not None:
                        _remove(load, order)
                        _add(loads[best_id], order)
                        moved = True
                        moves += 1
            if not moved:
                break
        return moves

    # ------------------------------------------------------------ public API
    def pack_orders_into_fleet(
        self,
        orders: list[dict[str, Any]],
        fleet: list[dict[str, Any]],
        customer_rules: list[dict[str, Any]] | None = None,
        max_stops: int | None = None,
    ) -> list[dict[str, Any]]:
        """Cluster orders into one multi-stop route per vehicle (see module docstring)."""
        max_stops = max_stops or settings.max_stops_per_vehicle
        vuc_only = vuc_only_customers(customer_rules or [])
        self.last_unallocated = []

        if not orders or not fleet:
            return []

        by_capacity = sorted(
            fleet,
            key=lambda v: (float(v["max_weight_kg"]), _VEHICLE_RANK.get(v.get("vehicle_type", "VUC"), 0)),
            reverse=True,
        )
        vuc_vehicles = [v for v in by_capacity if v.get("vehicle_type") == "VUC"]
        large_vehicles = [v for v in by_capacity if v.get("vehicle_type") != "VUC"]
        loads: dict[str, dict[str, Any]] = {v["vehicle_id"]: _new_load(v) for v in by_capacity}
        vehicle_by_id = {v["vehicle_id"]: v for v in by_capacity}

        restricted = [o for o in orders if _requires_vuc(o, vuc_only)]
        unrestricted = [o for o in orders if not _requires_vuc(o, vuc_only)]

        # 1. two-pass sweep
        deferred = self._sweep(restricted, vuc_vehicles, loads, vuc_only, max_stops)
        deferred += self._sweep(unrestricted, large_vehicles + vuc_vehicles, loads, vuc_only, max_stops)

        # 2. deferred orders -> nearest eligible route
        for order in sorted(deferred, key=lambda o: float(o.get("weight_kg", 0.0)), reverse=True):
            if not self._place_nearest(order, loads, vehicle_by_id, vuc_only, max_stops):
                self.last_unallocated.append(order)

        # 3. centroid refinement
        moves = self._refine(loads, vehicle_by_id, vuc_only, max_stops)

        for o in self.last_unallocated:
            logger.warning(
                "TMS: order %s (%s kg, %s m³, %s) could not be allocated today; kept PENDING.",
                o.get("order_id"),
                o.get("weight_kg"),
                o.get("volume_m3"),
                o.get("customer_name"),
            )
        result = [_finalise(load) for load in loads.values() if load["orders"]]
        logger.info(
            "TMS: %s orders clustered into %s routes (%s refinement moves, %s unallocated).",
            sum(load["stops_count"] for load in result),
            len(result),
            moves,
            len(self.last_unallocated),
        )
        return result


_fleet_service: FleetService | None = None


def get_fleet_service() -> FleetService:
    global _fleet_service
    if _fleet_service is None:
        _fleet_service = FleetService()
    return _fleet_service
