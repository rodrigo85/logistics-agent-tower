"""Unit tests for FleetService packing and vehicle allocation."""

from logistics_tower.services.fleet_service import FleetService


def test_fleet_packing_refrigerated_isolation():
    service = FleetService()
    fleet = [
        {
            "vehicle_id": "V-DRY",
            "model": "Dry VUC",
            "vehicle_type": "VUC",
            "max_weight_kg": 1500.0,
            "max_volume_m3": 10.0,
            "has_refrigeration": False,
            "driver_name": "Carlos",
            "current_status": "AVAILABLE",
        },
        {
            "vehicle_id": "V-REF",
            "model": "Ref VUC",
            "vehicle_type": "VUC",
            "max_weight_kg": 1500.0,
            "max_volume_m3": 10.0,
            "has_refrigeration": True,
            "driver_name": "Marcos",
            "current_status": "AVAILABLE",
        },
    ]

    orders = [
        {
            "order_id": "O-REF-1",
            "customer_name": "Peixaria",
            "weight_kg": 400.0,
            "volume_m3": 2.0,
            "cargo_type": "refrigerated",
        },
        {
            "order_id": "O-DRY-1",
            "customer_name": "Armazém",
            "weight_kg": 500.0,
            "volume_m3": 3.0,
            "cargo_type": "dry",
        },
    ]

    loads = service.pack_orders_into_fleet(orders=orders, fleet=fleet)
    assert len(loads) == 2

    # Check that refrigerated order is inside V-REF
    ref_load = next(l for l in loads if l["vehicle_id"] == "V-REF")
    assert any(o["order_id"] == "O-REF-1" for o in ref_load["orders"])
    assert ref_load["has_refrigeration"] is True
