"""Tests for the OR-Tools TSPTW routing service and the daily itinerary."""

from logistics_tower.config import settings
from logistics_tower.services.routing_service import (
    GoogleORToolsVRPTSolver,
    haversine_distance_meters,
    parse_clock,
)


def _order(oid: str, lat: float, lng: float, ws: str, we: str, **extra) -> dict:
    return {
        "order_id": oid,
        "customer_name": f"Cliente {oid}",
        "address": f"Rua {oid}, 100 - Itajaí",
        "lat": lat,
        "lng": lng,
        "window_start": ws,
        "window_end": we,
        "weight_kg": 250.0,
        "volume_m3": 1.2,
        "temperature_regime": "RESFRIADO",
        **extra,
    }


SIX_STOPS = [
    _order("A", -26.9185, -48.6492, "06:00", "10:00"),  # Fazenda
    _order("B", -26.8820, -48.6810, "07:00", "12:00"),  # Cordeiros
    _order("C", -26.9060, -48.6650, "06:00", "16:00"),  # Centro
    _order("D", -26.9520, -48.6320, "05:30", "08:30"),  # Praia Brava (bakery, early)
    _order("E", -26.9000, -48.7180, "08:00", "14:00"),  # Espinheiros
    _order("F", -26.9910, -48.6350, "07:00", "12:00"),  # Balneário Camboriú
]


def test_haversine_distance_with_circuity():
    dist_m = haversine_distance_meters(-26.9315, -48.7010, -26.9070, -48.6540)
    assert 4000 <= dist_m <= 10000


def test_plan_route_visits_every_stop_once_with_monotonic_times():
    solver = GoogleORToolsVRPTSolver()
    plan = solver.plan_route(SIX_STOPS)

    stops = plan["stops"]
    assert [s["sequence"] for s in stops] == list(range(1, 7))
    assert sorted(s["order_id"] for s in stops) == sorted(o["order_id"] for o in SIX_STOPS)

    assert plan["shift_start"] == settings.dock_start_time == "05:00"
    assert plan["departure"] == "06:00"
    clock = parse_clock(plan["departure"])
    for s in stops:
        arrival = parse_clock(s["estimated_arrival"])
        assert arrival >= clock
        assert parse_clock(s["service_start"]) >= arrival
        assert parse_clock(s["estimated_departure"]) > parse_clock(s["service_start"])
        clock = parse_clock(s["estimated_departure"])
    assert parse_clock(plan["shift_end"]) >= clock
    assert plan["total_distance_km"] > 0
    assert plan["total_duration_minutes"] > 0
    assert plan["within_shift_limit"] is True


def test_early_window_stop_is_served_first_and_waits_for_window_opening():
    """A single stop 5 minutes away with a 09:00 window: the truck waits, service starts at 09:00, on time."""
    solver = GoogleORToolsVRPTSolver()
    plan = solver.plan_route([_order("W", -26.9380, -48.7150, "09:00", "12:00")])

    stop = plan["stops"][0]
    assert stop["service_start"] == "09:00"
    assert stop["wait_min"] > 0
    assert stop["on_time"] is True


def test_late_arrival_is_flagged_not_hidden():
    solver = GoogleORToolsVRPTSolver()
    plan = solver.plan_route([_order("L", -27.0980, -48.9130, "05:00", "06:10")])  # Brusque, impossible window
    assert plan["stops"][0]["on_time"] is False


def test_itinerary_has_loading_stops_lunch_return_and_shift_end():
    solver = GoogleORToolsVRPTSolver()
    plan = solver.plan_route(SIX_STOPS)
    itinerary = plan["itinerary"]
    types = [step["type"] for step in itinerary]

    assert types[0] == "LOADING"
    assert itinerary[0]["time_start"] == "05:00"
    assert itinerary[0]["time_end"] == "06:00"
    assert types.count("UNLOADING") == 6
    assert types.count("TRANSIT_OUT") == 6
    assert types.count("LUNCH") == 1
    assert types.count("TRANSIT_RETURN") == 1
    assert types[-1] == "SHIFT_END"

    lunch = next(step for step in itinerary if step["type"] == "LUNCH")
    assert lunch["duration_min"] == settings.lunch_break_minutes
    if plan["lunch"]["after_sequence"] > 0:
        # taken on the road: only after the configured earliest time
        assert parse_clock(lunch["time_start"]) >= parse_clock(settings.lunch_earliest_time)
    else:
        # route finished early: taken at the CD right after the return leg
        assert types.index("LUNCH") == types.index("TRANSIT_RETURN") + 1


def test_lunch_taken_at_cd_when_route_ends_before_lunch_time():
    solver = GoogleORToolsVRPTSolver()
    plan = solver.plan_route([_order("Q", -26.9380, -48.7150, "06:00", "10:00")])
    assert plan["lunch"]["after_sequence"] == 0
    types = [step["type"] for step in plan["itinerary"]]
    assert types.index("LUNCH") > types.index("TRANSIT_RETURN")


def test_twelve_stops_solve_quickly_and_completely():
    solver = GoogleORToolsVRPTSolver()
    orders = [_order(f"S{i}", -26.88 - (i % 4) * 0.02, -48.62 - (i // 4) * 0.03, "06:00", "16:00") for i in range(12)]
    plan = solver.plan_route(orders)
    assert len(plan["stops"]) == 12
    assert all(s["on_time"] for s in plan["stops"])
