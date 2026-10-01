import pytest
import uuid
from app.db import Database


def test_idempotent_transaction_insert(tmp_path):
    db_file = tmp_path / "test_fraud.db"
    db = Database(db_url=f"sqlite:///{db_file}")

    txn_id = f"txn_{uuid.uuid4().hex[:10]}"
    
    # 1st insert
    res1 = db.save_transaction(
        txn_id=txn_id,
        card_id="card_111",
        merchant_id="merchant_abc",
        amount=150.0,
        txn_time="2026-05-01T10:00:00",
        channel="POS",
        lat=35.0,
        lon=-80.0,
        features_dict={"amt": 150.0},
        risk_score=0.15,
        anomaly_score=0.20,
        decision="approve",
        model_version="v1.0.0"
    )
    assert res1 is True

    # 2nd duplicate insert with same txn_id (should not raise duplicate key error)
    res2 = db.save_transaction(
        txn_id=txn_id,
        card_id="card_111",
        merchant_id="merchant_abc",
        amount=150.0,
        txn_time="2026-05-01T10:00:00",
        channel="POS",
        lat=35.0,
        lon=-80.0,
        features_dict={"amt": 150.0},
        risk_score=0.15,
        anomaly_score=0.20,
        decision="approve",
        model_version="v1.0.0"
    )
    assert res2 is True


def test_alert_lifecycle_and_audit_logging(tmp_path):
    db_file = tmp_path / "test_fraud.db"
    db = Database(db_url=f"sqlite:///{db_file}")

    txn_id = f"txn_{uuid.uuid4().hex[:10]}"
    db.save_transaction(
        txn_id=txn_id,
        card_id="card_222",
        merchant_id="merchant_xyz",
        amount=999.0,
        txn_time="2026-05-01T10:00:00",
        channel="WEB",
        lat=35.0,
        lon=-80.0,
        features_dict={"amt": 999.0},
        risk_score=0.88,
        anomaly_score=0.75,
        decision="block",
        model_version="v1.0.0"
    )

    alert_id = db.create_alert(
        txn_id=txn_id,
        risk_band="HIGH",
        decision="block",
        model_version="v1.0.0"
    )
    assert alert_id is not None

    # Resolve alert
    db.resolve_alert(
        alert_id=alert_id,
        status="confirmed_fraud",
        analyst_id="analyst_test",
        notes="High risk confirmed"
    )

    detail = db.get_alert_detail(alert_id)
    assert detail["status"] == "confirmed_fraud"
    assert detail["analyst_id"] == "analyst_test"
