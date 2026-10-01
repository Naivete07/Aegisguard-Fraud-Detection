from src.models.decision import DecisionEngine, DecisionThresholds


def test_decision_engine_approve():
    engine = DecisionEngine(DecisionThresholds(xgb_block_threshold=0.80, xgb_review_threshold=0.20, if_anomaly_threshold=0.65))
    res = engine.evaluate(risk_score=0.05, anomaly_score=0.30, amount=25.0)
    
    assert res.decision == "approve"
    assert res.risk_band == "LOW"
    assert res.is_alert is False


def test_decision_engine_block():
    engine = DecisionEngine(DecisionThresholds(xgb_block_threshold=0.80, xgb_review_threshold=0.20, if_anomaly_threshold=0.65))
    res = engine.evaluate(risk_score=0.92, anomaly_score=0.40, amount=1200.0)
    
    assert res.decision == "block"
    assert res.risk_band == "HIGH"
    assert res.is_alert is True


def test_decision_engine_review_supervised():
    engine = DecisionEngine(DecisionThresholds(xgb_block_threshold=0.80, xgb_review_threshold=0.20, if_anomaly_threshold=0.65))
    res = engine.evaluate(risk_score=0.45, anomaly_score=0.25, amount=400.0)
    
    assert res.decision == "review"
    assert res.risk_band == "MEDIUM"
    assert res.is_alert is True


def test_decision_engine_review_anomaly_only():
    engine = DecisionEngine(DecisionThresholds(xgb_block_threshold=0.80, xgb_review_threshold=0.20, if_anomaly_threshold=0.65))
    # Supervised model didn't flag, but anomaly score is elevated
    res = engine.evaluate(risk_score=0.08, anomaly_score=0.82, amount=650.0)
    
    assert res.decision == "review"
    assert res.risk_band == "MEDIUM"
    assert res.is_alert is True
    assert "Unsupervised anomaly" in res.trigger_reason
