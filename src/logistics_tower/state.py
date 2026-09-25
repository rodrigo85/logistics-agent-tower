"""
State definition for LangGraph Multi-Agent Logistics Orchestration.
"""

from typing import Any

from typing_extensions import TypedDict


class Order(TypedDict):
    order_id: str
    customer_name: str
    address: str
    lat: float
    lng: float
    weight_kg: float
    volume_m3: float
    cargo_type: str
    window_start: str
    window_end: str
    priority: str
    value_brl: float


class Vehicle(TypedDict):
    vehicle_id: str
    plate: str
    model: str
    vehicle_type: str
    max_weight_kg: float
    max_volume_m3: float
    has_refrigeration: bool
    driver_name: str
    driver_shift_max_hours: float
    current_status: str
    permitted_zones: list[str]


class VehicleLoad(TypedDict, total=False):
    vehicle_id: str
    plate: str
    vehicle_model: str
    vehicle_type: str
    driver_name: str
    driver_phone: str
    max_weight_kg: float
    max_volume_m3: float
    has_refrigeration: bool
    orders: list[dict[str, Any]]
    stops_count: int
    cities: list[str]
    total_weight_kg: float
    total_volume_m3: float
    weight_utilization_pct: float
    volume_utilization_pct: float
    cargo_types: list[str]


class RouteStop(TypedDict, total=False):
    sequence: int
    order_id: str
    customer_name: str
    address: str
    lat: float
    lng: float
    segment: str
    weight_kg: float
    volume_m3: float
    temperature_regime: str
    estimated_arrival: str
    service_start: str
    estimated_departure: str
    wait_min: int
    leg_distance_km: float
    leg_duration_min: int
    window_start: str
    window_end: str
    on_time: bool


class VehicleRoute(TypedDict, total=False):
    vehicle_id: str
    plate: str
    driver_name: str
    driver_phone: str
    vehicle_model: str
    vehicle_type: str
    max_weight_kg: float
    max_volume_m3: float
    total_distance_km: float
    total_estimated_duration_min: float
    shift_start: str
    shift_end: str
    within_shift_limit: bool
    stops: list[RouteStop]
    itinerary: list[dict[str, Any]]


class RiskWarning(TypedDict):
    level: str  # "INFO", "WARNING", "CRITICAL"
    category: str  # "OVERLOAD", "SLA_BREACH", "SHIFT_LIMIT", "ACCESS_VIOLATION", "SECURITY", "UNALLOCATED"
    entity_id: str
    description: str


class DispatchManifest(TypedDict):
    manifest_id: str
    cd_id: str
    timestamp: str
    total_orders_dispatched: int
    total_vehicles_assigned: int
    total_weight_kg: float
    total_volume_m3: float
    routes: list[VehicleRoute]
    status: str  # "DISPATCHED", "PENDING_APPROVAL", "REJECTED"


class LogisticsAgentState(TypedDict):
    # Context
    cd_id: str
    raw_orders: list[dict[str, Any]]
    available_fleet: list[dict[str, Any]]
    customer_rules: list[dict[str, Any]]

    # Step outputs from specialist agents
    load_allocation: list[VehicleLoad]
    unallocated_orders: list[dict[str, Any]]
    routes: list[VehicleRoute]
    risk_warnings: list[RiskWarning]

    # Human-in-the-Loop (HITL) gate
    auto_approve: bool  # request-level bypass (pipelines, evals); HITL_AUTO_APPROVE is the global one
    requires_human_approval: bool
    human_approval_reason: str
    human_verdict: str | None  # "APPROVED", "REJECTED", "OVERRIDE"
    human_feedback: str | None

    # Final result
    dispatch_manifest: DispatchManifest | None
    execution_log: list[str]
    messages: list[dict[str, Any]]
