"""Model Registry and Inference Pipeline.

Manages model lifecycle, artifact loading, hot-reloading, scoring execution,
and SHAP asynchronous explanation generation.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import joblib
import numpy as np
import pandas as pd

from src.config import ROOT
from src.features.online_features import ALL_FEATURE_COLUMNS, OnlineFeatureEngine
from src.models.decision import DecisionEngine, DecisionResult, DecisionThresholds
from src.models.drift import DriftDetector
from src.models.explainer import FraudExplainer

MODELS_DIR = ROOT / "models"


class ModelRegistry:
    """Singleton-style registry for active fraud detection models."""

    _instance: Optional[ModelRegistry] = None

    def __init__(self, model_path: Optional[Path] = None):
        self.model_path = model_path or (MODELS_DIR / "latest.joblib")
        self.bundle: Optional[Dict[str, Any]] = None
        self.xgb_model: Any = None
        self.iso_model: Any = None
        self.explainer: Optional[FraudExplainer] = None
        self.drift_detector: Optional[DriftDetector] = None
        self.decision_engine: Optional[DecisionEngine] = None
        self.feature_engine = OnlineFeatureEngine()
        self.model_version: str = "v0.0.0-uninitialized"
        self.is_loaded: bool = False
        
        # Try loading initial model if file exists
        if self.model_path.exists():
            self.load_model(self.model_path)

    @classmethod
    def get_instance(cls) -> ModelRegistry:
        if cls._instance is None:
            cls._instance = ModelRegistry()
        return cls._instance

    def load_model(self, model_path: Path) -> None:
        """Load and initialize model bundle from disk."""
        print(f"[ModelRegistry] Loading model bundle from {model_path}...")
        t0 = time.time()
        bundle = joblib.load(model_path)
        
        self.bundle = bundle
        self.model_version = bundle.get("model_version", "v1.0.0")
        self.xgb_model = bundle["xgb_model"]
        self.iso_model = bundle["iso_model"]
        self.feature_names = bundle.get("feature_names", ALL_FEATURE_COLUMNS)
        self.anomaly_cols = bundle.get("anomaly_cols", [])
        self.fill_medians = bundle.get("fill_medians", {})
        
        # Configure decision engine
        th_dict = bundle.get("thresholds", {})
        thresholds = DecisionThresholds(
            xgb_block_threshold=th_dict.get("xgb_block_threshold", 0.80),
            xgb_review_threshold=th_dict.get("xgb_review_threshold", 0.20),
            if_anomaly_threshold=th_dict.get("if_anomaly_threshold", 0.65),
        )
        self.decision_engine = DecisionEngine(thresholds=thresholds)

        # Configure explainer
        ref_stats = bundle.get("reference_stats", {})
        self.explainer = FraudExplainer(
            xgb_model=self.xgb_model,
            feature_names=self.feature_names,
            reference_stats=ref_stats
        )

        # Configure drift detector
        ref_dists = bundle.get("reference_distributions", {})
        self.drift_detector = DriftDetector(reference_distributions=ref_dists)

        self.is_loaded = True
        elapsed = (time.time() - t0) * 1000
        print(f"[ModelRegistry] Model {self.model_version} loaded successfully in {elapsed:.1f}ms")

    def score_transaction(
        self,
        txn: Dict[str, Any],
        update_state_after: bool = True
    ) -> Tuple[DecisionResult, Dict[str, Any], pd.DataFrame, float]:
        """Score a single transaction payload.
        
        Returns:
            decision_result: Approve / Review / Block decision object.
            features_dict: Computed feature key-values.
            features_df: Aligned 1-row DataFrame.
            latency_ms: Total scoring duration in milliseconds.
        """
        t0 = time.perf_counter()
        
        # 1. Compute real-time point-in-time features
        features_df, features_dict = self.feature_engine.compute_features(
            txn, update_state_after=update_state_after
        )

        # Reorder columns strictly
        X_row = features_df[self.feature_names].astype("float32")

        # 2. Supervised inference (XGBoost)
        risk_score = float(self.xgb_model.predict_proba(X_row)[0, 1])

        # 3. Unsupervised inference (Isolation Forest)
        X_anom = features_df[self.anomaly_cols].fillna(self.fill_medians)
        raw_if = float(-self.iso_model.score_samples(X_anom)[0])
        # Map raw IF score (typically 0.3 to 0.8) to normalized [0, 1] range for intuitive display
        anomaly_score = float(np.clip((raw_if - 0.35) / 0.40, 0.0, 1.0))

        # 4. Decision engine evaluation
        amount = float(txn.get("amt") or txn.get("amount") or 0.0)
        decision_res = self.decision_engine.evaluate(
            risk_score=risk_score,
            anomaly_score=anomaly_score,
            amount=amount
        )

        latency_ms = (time.perf_counter() - t0) * 1000.0
        return decision_res, features_dict, features_df, latency_ms

    def explain_flagged(
        self,
        features_df: pd.DataFrame,
        is_unsupervised_only: bool = False
    ) -> Dict[str, Any]:
        """Generate SHAP feature attribution and narrative for a flagged transaction."""
        if not self.explainer:
            return {}
        return self.explainer.explain(features_df, is_unsupervised_only=is_unsupervised_only)
