"""POST /score endpoint: real-time transaction scoring with async SHAP explanation dispatch."""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.db import Database, get_db
from app.schemas import ScoreResponse, TransactionRequest
from src.models.registry import ModelRegistry

router = APIRouter(prefix="", tags=["Scoring"])


def compute_and_save_shap(
    txn_id: str,
    features_df: Any,
    is_unsupervised_only: bool,
    db: Database
) -> None:
    """Async background task to calculate SHAP without adding latency to /score (PRD FR-14)."""
    try:
        registry = ModelRegistry.get_instance()
        shap_payload = registry.explain_flagged(
            features_df=features_df,
            is_unsupervised_only=is_unsupervised_only
        )
        if shap_payload:
            db.update_alert_shap(txn_id=txn_id, shap_dict=shap_payload)
    except Exception as e:
        print(f"[SHAP Worker Error] txn_id={txn_id}: {e}")


@router.post("/score", response_model=ScoreResponse)
def score_transaction(
    txn: TransactionRequest,
    background_tasks: BackgroundTasks,
    db: Database = Depends(get_db)
):
    """Score a single transaction synchronously against XGBoost + Isolation Forest.
    
    Target latency: p95 < 200 ms (NFR-1).
    Flagged alerts dispatch SHAP calculations to an asynchronous background worker (FR-14).
    """
    registry = ModelRegistry.get_instance()
    if not registry.is_loaded:
        raise HTTPException(status_code=503, detail="Scoring model not loaded")

    txn_dict = txn.model_dump()
    txn_id = txn.txn_id or f"txn_{uuid.uuid4().hex[:12]}"
    card_id = txn.get_card_id()
    amount = txn.get_amount()
    txn_time = txn.get_timestamp()
    channel = txn.channel or "POS"
    lat = float(txn.lat or 35.0)
    lon = float(txn.lon if txn.lon is not None else (txn.long or -90.0))

    # Synchronous real-time inference
    decision_res, feats_dict, feats_df, latency_ms = registry.score_transaction(
        txn=txn_dict,
        update_state_after=True
    )

    # Persist transaction to DB (idempotent write)
    db.save_transaction(
        txn_id=txn_id,
        card_id=card_id,
        merchant_id=str(txn.merchant),
        amount=amount,
        txn_time=txn_time,
        channel=channel,
        lat=lat,
        lon=lon,
        features_dict=feats_dict,
        risk_score=decision_res.risk_score,
        anomaly_score=decision_res.anomaly_score,
        decision=decision_res.decision,
        model_version=registry.model_version
    )

    alert_id = None
    if decision_res.is_alert:
        # Create alert entry
        alert_id = db.create_alert(
            txn_id=txn_id,
            risk_band=decision_res.risk_band,
            decision=decision_res.decision,
            model_version=registry.model_version
        )
        
        # Determine if this was flagged only by unsupervised layer
        is_unsupervised_only = (
            decision_res.risk_score < registry.decision_engine.thresholds.xgb_review_threshold
            and decision_res.anomaly_score >= registry.decision_engine.thresholds.if_anomaly_threshold
        )

        # Dispatch async SHAP calculation (off the critical path)
        background_tasks.add_task(
            compute_and_save_shap,
            txn_id=txn_id,
            features_df=feats_df,
            is_unsupervised_only=is_unsupervised_only,
            db=db
        )

    return ScoreResponse(
        txn_id=txn_id,
        decision=decision_res.decision,
        risk_score=round(decision_res.risk_score, 4),
        anomaly_score=round(decision_res.anomaly_score, 4),
        risk_band=decision_res.risk_band,
        is_alert=decision_res.is_alert,
        alert_id=alert_id,
        model_version=registry.model_version,
        trigger_reason=decision_res.trigger_reason,
        recommended_action=decision_res.recommended_action,
        latency_ms=round(latency_ms, 2),
        features={
            "dist_home_km": round(feats_dict.get("dist_home_km", 0.0), 1),
            "speed_kmh": round(feats_dict.get("speed_kmh", 0.0), 1),
            "amt_z": round(feats_dict.get("amt_z", 0.0), 2),
            "txn_count_1h": feats_dict.get("txn_count_1h", 0),
            "txn_count_24h": feats_dict.get("txn_count_24h", 0),
            "is_night": feats_dict.get("is_night", 0)
        }
    )
