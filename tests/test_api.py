"""Unit tests for FastAPI REST Endpoints."""

from fastapi.testclient import TestClient
from logistics_tower.api.main import app

client = TestClient(app)


def test_api_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_api_mcp_tools():
    res = client.get("/mcp/tools")
    assert res.status_code == 200
    tools = res.json()["tools"]
    assert len(tools) >= 4


def test_api_plan_and_resume_flow():
    # 1. Trigger plan
    plan_res = client.post("/dispatch/plan", json={"cd_id": "CD-ITAJAI-SC01", "auto_approve": False})
    assert plan_res.status_code == 200
    data = plan_res.json()
    thread_id = data["thread_id"]

    assert data["status"] == "AWAITING_HUMAN_APPROVAL"
    assert data["requires_approval"] is True

    # 2. Resume with approval
    resume_res = client.post(
        "/dispatch/resume",
        json={"thread_id": thread_id, "verdict": "APPROVED", "feedback": "Aprovado via API"},
    )
    assert resume_res.status_code == 200
    resumed_data = resume_res.json()
    assert resumed_data["status"] == "COMPLETED"
    assert resumed_data["manifest"] is not None


def test_api_generate_orders():
    res = client.post("/api/orders/generate?count=8")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["count"] == 8
    assert len(data["orders"]) == 8
    sample = data["orders"][0]
    assert "address" in sample
    assert "lat" in sample
    assert "lng" in sample
    assert sample["cargo_type"] in ["dry", "refrigerated"]

