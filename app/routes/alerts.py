"""GET /alerts, GET /alerts/{id}, and PATCH /alerts/{id} endpoints (PRD FR-18, FR-19, FR-20)."""
from __future__ import annotations

from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import Database, get_db
from app.schemas import (
    AlertDetailResponse,
    AlertListResponse,
    AlertResolutionRequest,
    AlertSummaryItem,
)
from src.models.registry import ModelRegistry

router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.get("", response_model=AlertListResponse)
def list_alerts(
    status: Optional[str] = Query(None, description="Filter by status: open, confirmed_fraud, false_positive, all"),
    decision: Optional[str] = Query(None, description="Filter by decision: block, review, all"),
    risk_band: Optional[str] = Query(None, description="Filter by risk band: HIGH, MEDIUM, LOW, all"),
    search: Optional[str] = Query(None, description="Search term for card_id, merchant, or txn_id"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("created_at", description="Field to sort by: created_at, risk_score, amount, txn_time"),
    sort_order: str = Query("DESC", description="Sort order: ASC or DESC"),
    db: Database = Depends(get_db)
):
    """Retrieve filtered and paginated fraud alerts for analyst triage (FR-18)."""
    rows, total = db.get_alerts(
        status=status,
        decision=decision,
        risk_band=risk_band,
        search=search,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order
    )

    items = [
        AlertSummaryItem(
            alert_id=r["alert_id"],
            txn_id=r["txn_id"],
            card_id=r["card_id"],
            merchant_id=r.get("merchant_id"),
            amount=float(r["amount"]),
            txn_time=str(r["txn_time"]),
            channel=r.get("channel"),
            status=r["status"],
            risk_band=r.get("risk_band", "MEDIUM"),
            decision=r.get("decision", "review"),
            risk_score=float(r.get("risk_score", 0.0)),
            anomaly_score=float(r.get("anomaly_score", 0.0)),
            model_version=r.get("model_version"),
            analyst_id=r.get("analyst_id"),
            created_at=str(r["created_at"])
        )
        for r in rows
    ]

    return AlertListResponse(
        total=total,
        alerts=items,
        limit=limit,
        offset=offset
    )


@router.get("/{alert_id}", response_model=AlertDetailResponse)
def get_alert_detail(
    alert_id: int,
    db: Database = Depends(get_db)
):
    """Get full case details including transaction, risk scores, and SHAP explanation (FR-19)."""
    detail = db.get_alert_detail(alert_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Alert #{alert_id} not found")

    # If SHAP explanation was not yet generated, generate it on-the-fly
    if not detail.get("shap_json") and detail.get("features_json"):
        try:
            registry = ModelRegistry.get_instance()
            feats_df = pd.DataFrame([detail["features_json"]])
            is_unsupervised_only = (
                detail.get("risk_score", 0.0) < 0.20
                and detail.get("anomaly_score", 0.0) >= 0.65
            )
            shap_payload = registry.explain_flagged(feats_df, is_unsupervised_only=is_unsupervised_only)
            detail["shap_json"] = shap_payload
            db.update_alert_shap(txn_id=detail["txn_id"], shap_dict=shap_payload)
        except Exception as e:
            print(f"[SHAP on-demand error] alert_id={alert_id}: {e}")

    return AlertDetailResponse(
        alert_id=detail["alert_id"],
        txn_id=detail["txn_id"],
        status=detail["status"],
        risk_band=detail.get("risk_band", "MEDIUM"),
        decision=detail.get("decision", "review"),
        risk_score=float(detail.get("risk_score", 0.0)),
        anomaly_score=float(detail.get("anomaly_score", 0.0)),
        model_version=detail.get("model_version"),
        analyst_id=detail.get("analyst_id"),
        resolution_notes=detail.get("resolution_notes"),
        resolved_at=str(detail.get("resolved_at")) if detail.get("resolved_at") else None,
        created_at=str(detail["created_at"]),
        card_id=detail["card_id"],
        merchant_id=detail.get("merchant_id"),
        amount=float(detail["amount"]),
        txn_time=str(detail["txn_time"]),
        channel=detail.get("channel"),
        lat=detail.get("lat"),
        long=detail.get("long"),
        features_json=detail.get("features_json"),
        shap_json=detail.get("shap_json")
    )


@router.patch("/{alert_id}")
def resolve_alert(
    alert_id: int,
    req: AlertResolutionRequest,
    db: Database = Depends(get_db)
):
    """Resolve an alert with confirmed_fraud or false_positive and log to audit trail (FR-20)."""
    valid_statuses = {"confirmed_fraud", "false_positive"}
    if req.status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{req.status}'. Must be one of {valid_statuses}"
        )

    detail = db.get_alert_detail(alert_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Alert #{alert_id} not found")

    success = db.resolve_alert(
        alert_id=alert_id,
        status=req.status,
        analyst_id=req.analyst_id,
        notes=req.notes or ""
    )

    return {
        "success": success,
        "alert_id": alert_id,
        "status": req.status,
        "analyst_id": req.analyst_id,
        "message": f"Alert #{alert_id} marked as {req.status}"
    }
