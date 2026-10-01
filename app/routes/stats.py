"""System statistics, drift monitoring, and model registry endpoints (PRD FR-21, FR-22)."""
from __future__ import annotations

import json
from typing import Any, Dict, List

import pandas as pd
from fastapi import APIRouter, Depends

from app.db import Database, get_db
from app.schemas import SummaryStatsResponse
from src.models.registry import ModelRegistry

router = APIRouter(prefix="", tags=["Analytics & Monitoring"])


@router.get("/stats", response_model=SummaryStatsResponse)
def get_system_stats(db: Database = Depends(get_db)):
    """Summary KPI metrics: open alerts, tiers, FPR, and prevented fraud amount (FR-21)."""
    stats = db.get_summary_stats()
    return SummaryStatsResponse(**stats)


@router.get("/drift")
def get_feature_drift(db: Database = Depends(get_db)):
    """Population Stability Index (PSI) drift monitoring against training baseline (FR-22)."""
    registry = ModelRegistry.get_instance()
    if not registry.drift_detector:
        return {"status": "uninitialized", "message": "Drift detector not initialized"}

    # Fetch recent transactions features
    with db.get_conn() as conn:
        cur = conn.execute("SELECT features_json FROM transactions ORDER BY created_at DESC LIMIT 500")
        rows = cur.fetchall()

    if not rows:
        return {
            "overall_status": "STABLE",
            "max_psi": 0.0,
            "drifted_features": [],
            "sample_size": 0,
            "message": "Insufficient recent transactions for drift check. Baseline is stable."
        }

    feat_list = []
    for r in rows:
        val = r["features_json"] if db.is_postgres else r["features_json"]
        if isinstance(val, str):
            try:
                feat_list.append(json.loads(val))
            except Exception:
                pass
        elif isinstance(val, dict):
            feat_list.append(val)

    if not feat_list:
        return {
            "overall_status": "STABLE",
            "max_psi": 0.0,
            "drifted_features": [],
            "sample_size": 0,
            "feature_metrics": {}
        }

    recent_df = pd.DataFrame(feat_list)
    drift_res = registry.drift_detector.evaluate_drift(recent_df)
    return drift_res


@router.get("/models")
def list_models(db: Database = Depends(get_db)):
    """List registered model versions, training metadata, and performance metrics."""
    registry = ModelRegistry.get_instance()
    registered = db.get_registered_models()
    
    # If empty in DB, inject active bundle info
    if not registered and registry.bundle:
        active_meta = {
            "model_version": registry.model_version,
            "model_type": registry.bundle.get("model_type", "hybrid_xgboost_isolation_forest"),
            "dataset": registry.bundle.get("dataset", "sparkov"),
            "trained_at": registry.bundle.get("trained_at"),
            "metrics_json": registry.bundle.get("metrics", {}),
            "artefact_path": str(registry.model_path)
        }
        db.register_model_version(
            model_version=active_meta["model_version"],
            model_type=active_meta["model_type"],
            dataset=active_meta["dataset"],
            metrics_dict=active_meta["metrics_json"],
            artefact_path=active_meta["artefact_path"]
        )
        registered = [active_meta]

    return {
        "active_version": registry.model_version,
        "models": registered
    }
