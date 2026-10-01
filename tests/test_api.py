import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["api"] == "ok"
    assert "active_model_version" in data


def test_score_endpoint():
    payload = {
        "cc_num": "4000123456789010",
        "amt": 45.50,
        "merchant": "fraud_Kirlin and Sons",
        "category": "grocery_pos",
        "channel": "POS",
        "lat": 35.2271,
        "long": -80.8431,
        "merch_lat": 35.2271,
        "merch_long": -80.8431,
        "trans_date_trans_time": "2026-05-15T14:30:00"
    }
    res = client.post("/score", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "decision" in data
    assert data["decision"] in ["approve", "review", "block"]
    assert "risk_score" in data
    assert "anomaly_score" in data
    assert data["latency_ms"] < 200  # NFR-1 target


def test_alerts_and_resolution_flow():
    # 1. Simulate an impossible travel alert
    sim_res = client.post("/simulate/batch", json={"scenario_type": "impossible_travel", "count": 2})
    assert sim_res.status_code == 200
    sim_data = sim_res.json()
    assert sim_data["generated_count"] == 2

    # 2. List alerts
    res = client.get("/alerts?limit=10")
    assert res.status_code == 200
    alerts_data = res.json()
    assert "alerts" in alerts_data
    assert alerts_data["total"] >= 1

    alert = alerts_data["alerts"][0]
    alert_id = alert["alert_id"]

    # 3. Get alert details (including SHAP)
    detail_res = client.get(f"/alerts/{alert_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["alert_id"] == alert_id
    assert "features_json" in detail

    # 4. Resolve alert
    patch_res = client.patch(f"/alerts/{alert_id}", json={
        "status": "confirmed_fraud",
        "analyst_id": "test_analyst",
        "notes": "Verified fraudulent transaction with cardholder"
    })
    assert patch_res.status_code == 200
    assert patch_res.json()["success"] is True


def test_stats_and_drift_endpoints():
    stats_res = client.get("/stats")
    assert stats_res.status_code == 200
    assert "total_transactions" in stats_res.json()

    drift_res = client.get("/drift")
    assert drift_res.status_code == 200
    assert "overall_status" in drift_res.json()
