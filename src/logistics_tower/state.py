"""
State definition for LangGraph Multi-Agent Logistics Orchestration.
"""

from typing import Any, Dict, List, Optional
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
    permitted_zones: List[str]


class VehicleLoad(TypedDict):
    vehicle_id: str
    orders: List[Dict[str, Any]]
    total_weight_kg: float
    total_volume_m3: float
    weight_utilization_pct: float
    volume_utilization_pct: float
    cargo_types: List[str]


class RouteStop(TypedDict):
    sequence: int
    order_id: str
    customer_name: str
    address: str
    estimated_arrival: str
    window_start: str
    window_end: str
    on_time: bool


class VehicleRoute(TypedDict):
    vehicle_id: str
    driver_name: str
    vehicle_model: str
    total_distance_km: float
    total_estimated_duration_min: float
    stops: List[RouteStop]


class RiskWarning(TypedDict):
    level: str  # "INFO", "WARNING", "CRITICAL"
    category: str  # "OVERLOAD", "SLA_BREACH", "ACCESS_VIOLATION", "SECURITY"
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
    routes: List[VehicleRoute]
    status: str  # "DISPATCHED", "PENDING_APPROVAL", "REJECTED"


class LogisticsAgentState(TypedDict):
    # Context
    cd_id: str
    raw_orders: List[Dict[str, Any]]
    available_fleet: List[Dict[str, Any]]
    customer_rules: List[Dict[str, Any]]

    # Step outputs from specialist agents
    load_allocation: List[VehicleLoad]
    routes: List[VehicleRoute]
    risk_warnings: List[RiskWarning]

    # Human-in-the-Loop (HITL) gate
    requires_human_approval: bool
    human_approval_reason: str
    human_verdict: Optional[str]  # "APPROVED", "REJECTED", "OVERRIDE"
    human_feedback: Optional[str]

    # Final result
    dispatch_manifest: Optional[DispatchManifest]
    execution_log: List[str]
    messages: List[Dict[str, Any]]
