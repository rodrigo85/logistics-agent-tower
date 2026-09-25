"""Tests for the FastAPI REST endpoints."""

from fastapi.testclient import TestClient

from logistics_tower.api.main import app
from logistics_tower.config import settings

client = TestClient(app)


def test_api_health_reports_version():
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["version"]


def test_api_mcp_tools():
    res = client.get("/mcp/tools")
    assert res.status_code == 200
    assert len(res.json()["tools"]) >= 4


def test_api_dashboard_data_exposes_fleet_and_orders():
    res = client.get("/api/dashboard-data")
    assert res.status_code == 200
    data = res.json()
    assert len(data["fleet"]) == 5
    assert len(data["orders"]) == 40
    assert data["cd_id"] == settings.default_cd_id


def test_api_plan_with_auto_approve_never_pauses(force_hitl):
    res = client.post("/dispatch/plan", json={"cd_id": settings.default_cd_id, "auto_approve": True})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "COMPLETED"
    assert data["requires_approval"] is False
    assert data["manifest"]["total_orders_dispatched"] == 40
    assert data["thread_id"].startswith("dispatch-")

    state = client.get(f"/api/thread-state/{data['thread_id']}").json()
    assert sum(len(r["stops"]) for r in state["routes"]) == 40


def test_api_plan_and_resume_flow(force_hitl):
    plan_res = client.post("/dispatch/plan", json={"cd_id": settings.default_cd_id, "auto_approve": False})
    assert plan_res.status_code == 200
    data = plan_res.json()
    thread_id = data["thread_id"]
    assert data["status"] == "AWAITING_HUMAN_APPROVAL"
    assert data["requires_approval"] is True
    assert data["risk_warnings"]

    status_res = client.get(f"/dispatch/{thread_id}")
    assert status_res.json()["status"] == "AWAITING_HUMAN_APPROVAL"

    resume_res = client.post(
        "/dispatch/resume",
        json={"thread_id": thread_id, "verdict": "APPROVED", "feedback": "Aprovado via API"},
    )
    assert resume_res.status_code == 200
    resumed = resume_res.json()
    assert resumed["status"] == "COMPLETED"
    assert resumed["manifest"]["total_orders_dispatched"] == 40

    itinerary_res = client.get("/api/vehicle/RLS-7B14/itinerary")
    assert itinerary_res.status_code == 200
    assert itinerary_res.json()["stops"]


def test_api_resume_unknown_thread_returns_404():
    res = client.post("/dispatch/resume", json={"thread_id": "does-not-exist", "verdict": "APPROVED"})
    assert res.status_code == 404


def test_api_generate_orders():
    res = client.post("/api/orders/generate?count=25")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["count"] == 25
    sample = data["orders"][0]
    assert sample["cargo_type"] == "refrigerated"
    assert sample["temperature_regime"] in {"RESFRIADO", "CONGELADO"}
    assert sample["segment"]
    assert {"address", "lat", "lng", "window_start", "window_end"} <= set(sample)
    assert len({o["customer_name"] for o in data["orders"]}) == 25


def test_api_generate_orders_is_capped_by_customer_pool():
    res = client.post("/api/orders/generate?count=120")
    assert res.status_code == 200
    assert res.json()["count"] == 56


def test_api_vehicle_itinerary_unknown_plate():
    res = client.get("/api/vehicle/XXX0000/itinerary")
    assert res.status_code == 404
