"""
Routing service: single-vehicle travelling-salesman with time windows (TSPTW)
solved by Google OR-Tools, plus the driver's daily itinerary.

Model (ADR-0006): one route per vehicle per day. Loading starts at
`DOCK_START_TIME` (05:00), the vehicle departs after `LOADING_TIME_MINUTES`,
visits every stop once (waiting when it arrives before the customer window
opens), takes the mandatory lunch break after the first stop completed after
`LUNCH_EARLIEST_TIME`, returns to the CD and closes the shift. Travel times use
Google Routes API v2 per leg when configured, otherwise haversine distance with
a road-circuity factor at an urban average speed.
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Any

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from logistics_tower.config import settings
from logistics_tower.services.traffic_service import get_traffic_service

logger = logging.getLogger(__name__)

_BASE_DATE = datetime(2000, 1, 1)
LATE_PENALTY_PER_MINUTE = 100  # soft time-window penalty (cost units per minute late)
MAX_WAIT_MINUTES = 240  # slack allowed for arriving before a window opens
MIN_LEG_MINUTES = 3


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """Road distance estimate: great-circle distance times the configured circuity factor."""
    r = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return int(r * c * settings.road_circuity_factor)


def travel_minutes(distance_m: int) -> int:
    metres_per_minute = settings.urban_speed_kmh * 1000.0 / 60.0
    return max(MIN_LEG_MINUTES, round(distance_m / metres_per_minute))


def parse_clock(value: str) -> datetime:
    hours, minutes = value.split(":")
    return _BASE_DATE.replace(hour=int(hours), minute=int(minutes))


def _fmt(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def _minutes_between(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds() // 60)


class GoogleORToolsVRPTSolver:
    """OR-Tools based sequencing of one vehicle's stops plus timeline and itinerary."""

    def __init__(self, cd_lat: float | None = None, cd_lng: float | None = None):
        self.cd_lat = settings.cd_lat if cd_lat is None else cd_lat
        self.cd_lng = settings.cd_lng if cd_lng is None else cd_lng

    # ------------------------------------------------------------------ legs
    def _leg(self, lat1: float, lng1: float, lat2: float, lng2: float) -> tuple[int, int, bool]:
        """(distance_m, duration_min, traffic_aware) for one leg."""
        svc = get_traffic_service()
        if svc.is_available():
            route = svc.get_route_with_traffic(lat1, lng1, lat2, lng2)
            if route:
                return int(route["distance_meters"]), max(MIN_LEG_MINUTES, round(route["duration_minutes"])), True
        distance = haversine_distance_meters(lat1, lng1, lat2, lng2)
        return distance, travel_minutes(distance), False

    # -------------------------------------------------------------- sequence
    def _solve_sequence(self, orders: list[dict[str, Any]], departure: datetime) -> list[int]:
        """Return the visiting order (indexes into `orders`) minimising distance under soft time windows."""
        n = len(orders)
        if n == 1:
            return [0]

        service = settings.unloading_time_minutes
        # Planning horizon is the rest of the calendar day: the legal shift limit is audited by the
        # timeline (SHIFT_LIMIT warning) rather than imposed as a hard bound, so long routes are still
        # sequenced optimally instead of falling back to the greedy heuristic.
        horizon = 24 * 60 - (departure.hour * 60 + departure.minute)
        points = [(self.cd_lat, self.cd_lng)] + [(float(o["lat"]), float(o["lng"])) for o in orders]

        dist: list[list[int]] = [[0] * (n + 1) for _ in range(n + 1)]
        time: list[list[int]] = [[0] * (n + 1) for _ in range(n + 1)]
        for i in range(n + 1):
            for j in range(n + 1):
                if i == j:
                    continue
                d = haversine_distance_meters(points[i][0], points[i][1], points[j][0], points[j][1])
                dist[i][j] = d
                time[i][j] = travel_minutes(d) + (service if i > 0 else 0)

        windows: list[tuple[int, int]] = []
        for o in orders:
            ws = max(0, _minutes_between(departure, parse_clock(o["window_start"])))
            we = _minutes_between(departure, parse_clock(o["window_end"]))
            ws = min(ws, horizon - 1)
            we = max(ws + 1, min(we, horizon))
            windows.append((ws, we))

        manager = pywrapcp.RoutingIndexManager(n + 1, 1, 0)
        routing = pywrapcp.RoutingModel(manager)

        def distance_callback(from_index: int, to_index: int) -> int:
            return dist[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]

        def time_callback(from_index: int, to_index: int) -> int:
            return time[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]

        routing.SetArcCostEvaluatorOfAllVehicles(routing.RegisterTransitCallback(distance_callback))
        routing.AddDimension(routing.RegisterTransitCallback(time_callback), MAX_WAIT_MINUTES, horizon, True, "Time")
        time_dim = routing.GetDimensionOrDie("Time")

        for node in range(1, n + 1):
            index = manager.NodeToIndex(node)
            ws, we = windows[node - 1]
            time_dim.CumulVar(index).SetRange(ws, horizon)
            time_dim.SetCumulVarSoftUpperBound(index, we, LATE_PENALTY_PER_MINUTE)
            routing.AddVariableMinimizedByFinalizer(time_dim.CumulVar(index))
        routing.AddVariableMinimizedByFinalizer(time_dim.CumulVar(routing.End(0)))

        params = pywrapcp.DefaultRoutingSearchParameters()
        params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        if n > 8:
            params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
            params.time_limit.FromMilliseconds(800)
        else:
            params.time_limit.FromMilliseconds(300)

        solution = routing.SolveWithParameters(params)
        if solution is None:
            logger.warning("OR-Tools: no feasible TSPTW solution for %s stops; using greedy fallback.", n)
            return self._greedy_sequence(orders)

        sequence: list[int] = []
        index = routing.Start(0)
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if node > 0:
                sequence.append(node - 1)
            index = solution.Value(routing.NextVar(index))
        logger.info("OR-Tools: sequenced %s stops (objective %s).", n, solution.ObjectiveValue())
        return sequence

    def _greedy_sequence(self, orders: list[dict[str, Any]]) -> list[int]:
        """Earliest-window-end first, ties by proximity to the previous stop."""
        remaining = list(range(len(orders)))
        sequence: list[int] = []
        lat, lng = self.cd_lat, self.cd_lng
        while remaining:
            nxt = min(
                remaining,
                key=lambda i: (
                    parse_clock(orders[i]["window_end"]),
                    haversine_distance_meters(lat, lng, float(orders[i]["lat"]), float(orders[i]["lng"])),
                ),
            )
            sequence.append(nxt)
            remaining.remove(nxt)
            lat, lng = float(orders[nxt]["lat"]), float(orders[nxt]["lng"])
        return sequence

    # -------------------------------------------------------------- timeline
    def _timeline(self, ordered: list[dict[str, Any]], dock_start: datetime, departure: datetime) -> dict[str, Any]:
        service = settings.unloading_time_minutes
        lunch_earliest = parse_clock(settings.lunch_earliest_time)
        lunch_len = settings.lunch_break_minutes

        clock = departure
        prev_lat, prev_lng = self.cd_lat, self.cd_lng
        total_m = 0
        traffic_used = False
        stops: list[dict[str, Any]] = []
        lunch_start: datetime | None = None
        lunch_end: datetime | None = None
        lunch_after = 0

        for seq, o in enumerate(ordered, start=1):
            d_m, t_min, traffic = self._leg(prev_lat, prev_lng, float(o["lat"]), float(o["lng"]))
            traffic_used = traffic_used or traffic
            total_m += d_m
            leg_start = clock
            arrival = clock + timedelta(minutes=t_min)
            w_start, w_end = parse_clock(o["window_start"]), parse_clock(o["window_end"])
            service_start = max(arrival, w_start)
            wait = _minutes_between(arrival, service_start)
            on_time = service_start <= w_end
            departure_from_stop = service_start + timedelta(minutes=service)

            stop = {
                "sequence": seq,
                "order_id": o.get("order_id") or o.get("order_number", f"ORD-{seq}"),
                "customer_name": o["customer_name"],
                "address": o.get("address", ""),
                "lat": float(o["lat"]),
                "lng": float(o["lng"]),
                "segment": o.get("segment"),
                "weight_kg": o.get("weight_kg"),
                "volume_m3": o.get("volume_m3"),
                "temperature_regime": o.get("temperature_regime"),
                "leg_start": _fmt(leg_start),
                "leg_distance_km": round(d_m / 1000.0, 1),
                "leg_duration_min": t_min,
                "estimated_arrival": _fmt(arrival),
                "service_start": _fmt(service_start),
                "estimated_departure": _fmt(departure_from_stop),
                "wait_min": wait,
                "window_start": o["window_start"],
                "window_end": o["window_end"],
                "on_time": on_time,
                "traffic_aware": traffic,
                "lunch_after": False,
            }
            clock = departure_from_stop
            prev_lat, prev_lng = float(o["lat"]), float(o["lng"])

            if lunch_start is None and clock >= lunch_earliest:
                lunch_start, lunch_end, lunch_after = clock, clock + timedelta(minutes=lunch_len), seq
                stop["lunch_after"] = True
                clock = lunch_end
            stops.append(stop)

        d_m, t_min, traffic = self._leg(prev_lat, prev_lng, self.cd_lat, self.cd_lng)
        traffic_used = traffic_used or traffic
        total_m += d_m
        return_start = clock
        return_end = clock + timedelta(minutes=t_min)
        return_km = round(d_m / 1000.0, 1)
        clock = return_end
        if lunch_start is None or lunch_end is None:
            lunch_start, lunch_end, lunch_after = clock, clock + timedelta(minutes=lunch_len), 0
            clock = lunch_end

        assert lunch_start is not None and lunch_end is not None  # narrowed above
        shift_end = clock
        total_min = _minutes_between(dock_start, shift_end)
        return {
            "stops": stops,
            "total_distance_km": round(total_m / 1000.0, 1),
            "total_duration_minutes": float(total_min),
            "shift_start": _fmt(dock_start),
            "departure": _fmt(departure),
            "shift_end": _fmt(shift_end),
            "within_shift_limit": total_min <= settings.max_shift_hours * 60,
            "traffic_aware": traffic_used,
            "lunch": {
                "start": _fmt(lunch_start),
                "end": _fmt(lunch_end),
                "after_sequence": lunch_after,
            },
            "return_leg": {
                "start": _fmt(return_start),
                "end": _fmt(return_end),
                "distance_km": return_km,
                "duration_min": t_min,
            },
            "_dock_start": dock_start,
            "_departure": departure,
        }

    # ------------------------------------------------------------- itinerary
    @staticmethod
    def _itinerary(plan: dict[str, Any]) -> list[dict[str, Any]]:
        stops = plan["stops"]
        lunch = plan["lunch"]
        ret = plan["return_leg"]
        steps: list[dict[str, Any]] = []
        step = 1
        total_weight = round(sum(float(s.get("weight_kg") or 0.0) for s in stops), 1)
        total_volume = round(sum(float(s.get("volume_m3") or 0.0) for s in stops), 2)

        steps.append(
            {
                "step": step,
                "type": "LOADING",
                "icon": "package",
                "title": "Carregamento no CD Itajaí",
                "time_start": plan["shift_start"],
                "time_end": plan["departure"],
                "duration_min": settings.loading_time_minutes,
                "location": "Doca de refrigerados - CD Itajaí (Rod. Antônio Heil)",
                "description": (
                    f"Conferência de NFs, estufagem por ordem inversa de entrega e pré-resfriamento do baú "
                    f"({len(stops)} paradas, {total_weight} kg, {total_volume} m³)."
                ),
                "badge": "Doca CD",
                "badge_color": "blue",
                "weight_kg": total_weight,
                "volume_m3": total_volume,
            }
        )
        step += 1

        lunch_block = {
            "type": "LUNCH",
            "icon": "utensils",
            "title": "Intervalo de Almoço Obrigatório",
            "time_start": lunch["start"],
            "time_end": lunch["end"],
            "duration_min": settings.lunch_break_minutes,
            "description": "Intervalo intrajornada de 1 hora para alimentação e repouso (Art. 235-C da CLT / Lei 13.103/2015).",
            "badge": "Almoço 1h",
            "badge_color": "amber",
        }

        for s in stops:
            steps.append(
                {
                    "step": step,
                    "type": "TRANSIT_OUT",
                    "icon": "truck",
                    "title": f"Deslocamento para a parada {s['sequence']}",
                    "time_start": s["leg_start"],
                    "time_end": s["estimated_arrival"],
                    "duration_min": s["leg_duration_min"],
                    "location": f"➔ {s['customer_name']}",
                    "description": (
                        f"{s['leg_distance_km']} km"
                        + (
                            " com tráfego ao vivo (Google Maps)"
                            if s.get("traffic_aware")
                            else " (estimativa rodoviária)"
                        )
                        + (f"; espera de {s['wait_min']} min até a abertura da janela" if s["wait_min"] > 0 else "")
                    ),
                    "badge": "Em Trânsito",
                    "badge_color": "indigo",
                    "distance_km": s["leg_distance_km"],
                    "sequence": s["sequence"],
                }
            )
            step += 1
            steps.append(
                {
                    "step": step,
                    "type": "UNLOADING",
                    "icon": "map-pin",
                    "title": f"Entrega {s['sequence']}: {s['customer_name']}",
                    "time_start": s["service_start"],
                    "time_end": s["estimated_departure"],
                    "duration_min": settings.unloading_time_minutes,
                    "location": s["address"],
                    "description": (
                        f"Descarga refrigerada ({s.get('temperature_regime') or 'RESFRIADO'}), conferência de temperatura "
                        f"e assinatura do canhoto digital."
                    ),
                    "badge": "✓ No Prazo" if s["on_time"] else "Atraso SLA",
                    "badge_color": "emerald" if s["on_time"] else "rose",
                    "order_id": s["order_id"],
                    "window": f"{s['window_start']} - {s['window_end']}",
                    "eta": s["estimated_arrival"],
                    "weight_kg": s.get("weight_kg"),
                    "volume_m3": s.get("volume_m3"),
                    "sequence": s["sequence"],
                    "on_time": s["on_time"],
                }
            )
            step += 1
            if s.get("lunch_after"):
                steps.append({"step": step, "location": "Ponto de apoio próximo ao cliente", **lunch_block})
                step += 1

        steps.append(
            {
                "step": step,
                "type": "TRANSIT_RETURN",
                "icon": "rotate-ccw",
                "title": "Retorno ao CD Itajaí",
                "time_start": ret["start"],
                "time_end": ret["end"],
                "duration_min": ret["duration_min"],
                "location": "➔ CD Itajaí",
                "description": f"Retorno do veículo vazio para a base ({ret['distance_km']} km).",
                "badge": "Retorno",
                "badge_color": "slate",
                "distance_km": ret["distance_km"],
            }
        )
        step += 1
        if lunch["after_sequence"] == 0:
            steps.append({"step": step, "location": "Refeitório do CD Itajaí", **lunch_block})
            step += 1

        hours = round(plan["total_duration_minutes"] / 60.0, 1)
        within = plan["within_shift_limit"]
        steps.append(
            {
                "step": step,
                "type": "SHIFT_END",
                "icon": "check-circle",
                "title": "Encerramento da Jornada Diária",
                "time_start": plan["shift_end"],
                "time_end": plan["shift_end"],
                "duration_min": 0,
                "location": "Pátio CD Itajaí",
                "description": (
                    f"Jornada de {hours}h ({plan['shift_start']} ➔ {plan['shift_end']}). "
                    + (
                        f"Dentro do limite legal de {settings.max_shift_hours:g}h (Lei 13.103/2015)."
                        if within
                        else f"EXCEDE o limite legal de {settings.max_shift_hours:g}h; requer aprovação do despachante."
                    )
                ),
                "badge": "Jornada Concluída" if within else "Jornada Excedida",
                "badge_color": "emerald" if within else "rose",
            }
        )
        return steps

    # ------------------------------------------------------------ public API
    def plan_route(self, orders: list[dict[str, Any]], start_time_str: str | None = None) -> dict[str, Any]:
        """Sequence, time and describe a vehicle's daily route."""
        dock_start = parse_clock(start_time_str or settings.dock_start_time)
        departure = dock_start + timedelta(minutes=settings.loading_time_minutes)
        if not orders:
            return {
                "stops": [],
                "total_distance_km": 0.0,
                "total_duration_minutes": 0.0,
                "shift_start": _fmt(dock_start),
                "departure": _fmt(departure),
                "shift_end": _fmt(departure),
                "within_shift_limit": True,
                "traffic_aware": False,
                "itinerary": [],
            }
        sequence = self._solve_sequence(orders, departure)
        plan = self._timeline([orders[i] for i in sequence], dock_start, departure)
        plan.pop("_dock_start", None)
        plan.pop("_departure", None)
        plan["itinerary"] = self._itinerary(plan)
        return plan

    def solve_vehicle_route(
        self, orders: list[dict[str, Any]], start_time_str: str | None = None
    ) -> tuple[list[dict[str, Any]], float, float]:
        """Compatibility wrapper: (stops, total_distance_km, total_duration_minutes)."""
        plan = self.plan_route(orders, start_time_str)
        return plan["stops"], plan["total_distance_km"], plan["total_duration_minutes"]

    optimize_stops_sequence = solve_vehicle_route

    def build_daily_itinerary(
        self,
        orders: list[dict[str, Any]],
        stops: list[dict[str, Any]] | None = None,
        start_time_str: str | None = None,
        vehicle: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Compatibility wrapper returning only the itinerary steps."""
        return self.plan_route(orders, start_time_str)["itinerary"]


_solver_instance: GoogleORToolsVRPTSolver | None = None


def get_routing_service() -> GoogleORToolsVRPTSolver:
    global _solver_instance
    if _solver_instance is None:
        _solver_instance = GoogleORToolsVRPTSolver()
    return _solver_instance
