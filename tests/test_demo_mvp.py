from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_mvp_manifest_exposes_demo_contract() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/demo/mvp")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "smart-manufacturing-mvp"
    assert data["status"] in {"ready", "degraded"}
    assert set(data["health"]) == {"database_ready", "model_ready", "graph_ready"}
    assert len(data["agents"]) == 5
    assert len(data["scenarios"]) >= 5
    assert len(data["acceptance_flow"]) >= 5


def test_mvp_manifest_has_collaborative_scenario() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/demo/mvp")
    scenarios = response.json()["scenarios"]

    assert any(item["expected_mode"] == "collaborative" for item in scenarios)
    assert all("request_text" in item and item["request_text"] for item in scenarios)
