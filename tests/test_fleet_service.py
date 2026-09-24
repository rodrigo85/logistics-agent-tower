"""Tests for the sweep-based multi-drop allocation (FleetService)."""

from logistics_tower.config import settings
from logistics_tower.db.repository import get_repository
from logistics_tower.services.fleet_service import FleetService, polar_angle

CD = (settings.cd_lat, settings.cd_lng)


def _vehicle(vid: str, vtype: str, weight: float, volume: float, refrigerated: bool = True) -> dict:
    return {
        "vehicle_id": vid,
        "plate": vid.replace("-", "")[-7:],
        "model": f"{vtype} test",
        "vehicle_type": vtype,
        "max_weight_kg": weight,
        "max_volume_m3": volume,
        "has_refrigeration": refrigerated,
        "driver_name": "Tester",
        "current_status": "AVAILABLE",
    }


def _order(oid: str, lat: float, lng: float, weight: float = 200.0, volume: float = 1.0, **extra) -> dict:
    base = {
        "order_id": oid,
        "customer_name": f"Cliente {oid}",
        "lat": lat,
        "lng": lng,
        "weight_kg": weight,
        "volume_m3": volume,
        "cargo_type": "refrigerated",
        "city": extra.pop("city", "Itajaí"),
    }
    base.update(extra)
    return base


def test_polar_angle_is_in_range():
    assert 0.0 <= polar_angle(-26.90, -48.60, *CD) < 6.3
    assert 0.0 <= polar_angle(-27.10, -48.95, *CD) < 6.3


def test_sweep_groups_geographically_adjacent_stops():
    """Two clear clusters (east coast vs. Brusque, west) must not be mixed inside one vehicle."""
    service = FleetService()
    east = [_order(f"E{i}", -26.90 - i * 0.004, -48.63 + i * 0.003, city="Itajaí") for i in range(6)]
    west = [_order(f"W{i}", -27.09 - i * 0.004, -48.91 - i * 0.003, city="Brusque") for i in range(6)]
    fleet = [_vehicle("V-A", "TOCO", 6000.0, 32.0), _vehicle("V-B", "TOCO", 6000.0, 32.0)]

    loads = service.pack_orders_into_fleet(orders=east + west, fleet=fleet, max_stops=6)

    assert len(loads) == 2
    for load in loads:
        cities = {o["city"] for o in load["orders"]}
        assert len(cities) == 1, f"vehicle {load['vehicle_id']} mixed clusters: {cities}"
        assert load["stops_count"] == 6
    assert not service.last_unallocated


def test_one_route_per_vehicle_and_capacity_never_exceeded():
    service = FleetService()
    fleet = [_vehicle("V-SMALL", "VUC", 1000.0, 6.0)]
    orders = [_order(f"O{i}", -26.91 - i * 0.002, -48.66, weight=300.0, volume=1.5) for i in range(5)]

    loads = service.pack_orders_into_fleet(orders=orders, fleet=fleet)

    assert len(loads) == 1
    load = loads[0]
    assert load["stops_count"] == 3  # 3 x 300 kg = 900 kg <= 1000 kg; the 4th would exceed
    assert load["total_weight_kg"] <= load["max_weight_kg"]
    assert load["weight_utilization_pct"] <= 100.0
    assert len(service.last_unallocated) == 2


def test_max_stops_per_vehicle_is_respected():
    service = FleetService()
    fleet = [_vehicle("V-BIG", "TRUCK", 13000.0, 55.0)]
    orders = [_order(f"O{i}", -26.90 - i * 0.001, -48.65, weight=50.0, volume=0.2) for i in range(20)]

    loads = service.pack_orders_into_fleet(orders=orders, fleet=fleet, max_stops=12)

    assert loads[0]["stops_count"] == 12
    assert len(service.last_unallocated) == 8


def test_vuc_only_customer_never_goes_on_a_truck():
    service = FleetService()
    fleet = [_vehicle("V-TRUCK", "TRUCK", 13000.0, 55.0), _vehicle("V-VUC", "VUC", 1600.0, 11.0)]
    orders = [
        _order("O-VUC", -26.9185, -48.6492, customer_name="Supermercado Bistek - Fazenda", max_vehicle_allowed="VUC"),
        _order("O-ANY", -26.9190, -48.6500, customer_name="Cooper São João"),
    ]
    rules = [
        {
            "customer_name": "Supermercado Bistek - Fazenda",
            "rule_category": "ACCESS_RESTRICTION",
            "content": "Rua estreita. Apenas veículos VUC autorizados.",
            "max_vehicle_allowed": "VUC",
        }
    ]

    loads = service.pack_orders_into_fleet(orders=orders, fleet=fleet, customer_rules=rules)
    by_vehicle = {load["vehicle_id"]: [o["order_id"] for o in load["orders"]] for load in loads}

    assert "O-VUC" in by_vehicle.get("V-VUC", [])
    assert "O-VUC" not in by_vehicle.get("V-TRUCK", [])


def test_refrigerated_orders_never_go_on_dry_vehicles():
    service = FleetService()
    fleet = [_vehicle("V-DRY", "TOCO", 6000.0, 32.0, refrigerated=False), _vehicle("V-REF", "VUC", 1600.0, 11.0)]
    orders = [_order("O1", -26.91, -48.66), _order("O2", -26.92, -48.67)]

    loads = service.pack_orders_into_fleet(orders=orders, fleet=fleet)

    assert [load["vehicle_id"] for load in loads] == ["V-REF"]
    assert loads[0]["stops_count"] == 2


def test_seeded_dataset_is_fully_allocated_on_the_five_trucks():
    """The canonical 40-order seed must fit the refrigerated fleet with <= 12 stops per route."""
    repo = get_repository()
    service = FleetService()
    fleet = repo.get_available_fleet(settings.default_cd_id)
    orders = repo.get_pending_orders(settings.default_cd_id)
    rules = repo.get_all_customer_rules()

    assert len(fleet) == 5
    assert all(v["has_refrigeration"] for v in fleet)
    assert len(orders) == 40
    assert all(o["cargo_type"] == "refrigerated" for o in orders)

    loads = service.pack_orders_into_fleet(orders=orders, fleet=fleet, customer_rules=rules)

    assert sum(load["stops_count"] for load in loads) == 40
    assert not service.last_unallocated
    for load in loads:
        assert 1 <= load["stops_count"] <= settings.max_stops_per_vehicle
        assert load["weight_utilization_pct"] <= 100.0
        assert load["volume_utilization_pct"] <= 100.0
