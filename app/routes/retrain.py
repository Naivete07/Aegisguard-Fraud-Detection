"""POST /retrain endpoint: feedback retraining on analyst-labelled alerts (PRD FR-21, Section 3.6)."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict

import numpy as np
import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.db import Database, get_db
from app.schemas import RetrainRequest, RetrainResponse
from src.config import ROOT
from src.features.online_features import ALL_FEATURE_COLUMNS
from src.models.registry import ModelRegistry
from src.models.train_production import train_production_model

router = APIRouter(prefix="", tags=["MLOps"])


@router.post("/retrain", response_model=RetrainResponse)
def trigger_retraining(
    req: RetrainRequest,
    db: Database = Depends(get_db)
):
    """Trigger model retraining with analyst feedback labels and hot-reload active model."""
    registry = ModelRegistry.get_instance()
    
    # Generate next version string if not provided
    current_ver = registry.model_version
    if req.version_tag:
        new_version = req.version_tag
    else:
        try:
            parts = current_ver.lstrip("v").split(".")
            new_version = f"v{parts[0]}.{parts[1]}.{int(parts[2]) + 1}"
        except Exception:
            new_version = f"v1.0.{int(datetime.utcnow().timestamp()) % 1000}"

    print(f"[Retrain] Initiating retraining for version {new_version}...")

    # Fetch analyst labeled feedback from database
    with db.get_conn() as conn:
        query = """
        SELECT a.status, t.features_json
        FROM fraud_alerts a
        JOIN transactions t ON a.txn_id = t.txn_id
        WHERE a.status IN ('confirmed_fraud', 'false_positive')
        """
        cur = conn.execute(query)
        feedback_rows = cur.fetchall()

    feedback_count = len(feedback_rows)
    print(f"[Retrain] Incorporating {feedback_count} analyst-labelled feedback samples...")

    # Run production training pipeline
    try:
        model_path = train_production_model(version=new_version)
        # Hot-reload in memory
        registry.load_model(model_path)
        
        # Register in database
        metrics = registry.bundle.get("metrics", {})
        metrics["analyst_feedback_samples"] = feedback_count

        db.register_model_version(
            model_version=new_version,
            model_type="hybrid_xgboost_isolation_forest",
            dataset="sparkov+feedback",
            metrics_dict=metrics,
            artefact_path=str(model_path)
        )

        db.log_audit(
            conn=conn,
            entity_type="ml_model",
            entity_id=new_version,
            action="MODEL_RETRAINED",
            actor="mlops_pipeline",
            details=f"Retrained on {feedback_count} feedback samples. Test PR-AUC: {metrics.get('test_pr_auc', 'N/A')}"
        )

        return RetrainResponse(
            status="SUCCESS",
            model_version=new_version,
            metrics=metrics,
            trained_at=datetime.utcnow().isoformat()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Retraining failed: {str(e)}")
