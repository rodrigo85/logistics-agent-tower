"""Unit tests for Google OR-Tools CVRPTW Routing Solver."""

from logistics_tower.services.routing_service import GoogleORToolsVRPTSolver, haversine_distance_meters


def test_haversine_distance():
    # Distance between Itajaí CD (-26.9315, -48.7010) and Porto de Itajaí (-26.9070, -48.6540)
    dist_m = haversine_distance_meters(-26.9315, -48.7010, -26.9070, -48.6540)
    # Between 4000m and 9000m (with 1.35x circuity factor)
    assert 4000 <= dist_m <= 10000


def test_solve_vehicle_route_ortools():
    solver = GoogleORToolsVRPTSolver(cd_lat=-26.9315, cd_lng=-48.7010)
    orders = [
        {
            "order_id": "ORD-ITJ-001",
            "customer_name": "Supermercado Bistek - Fazenda",
            "address": "Rua Sete de Setembro, 1200",
            "lat": -26.9185,
            "lng": -48.6492,
            "window_start": "07:30",
            "window_end": "11:00",
            "priority": "VIP",
        },
        {
            "order_id": "ORD-ITJ-005",
            "customer_name": "Farmácia Preço Popular - São Vicente",
            "address": "Rua Estefano José Vanolli, 920",
            "lat": -26.9045,
            "lng": -48.6935,
            "window_start": "09:00",
            "window_end": "13:30",
            "priority": "STANDARD",
        },
    ]

    stops, total_km, total_min = solver.solve_vehicle_route(orders, start_time_str="07:00")
    assert len(stops) == 2
    assert total_km > 0
    assert total_min > 0
    assert stops[0]["sequence"] == 1
    assert stops[1]["sequence"] == 2
