"""Train and export the production hybrid model bundle (XGBoost + Isolation Forest + SHAP + Drift baseline).

Saves artifact to models/latest.joblib and models/production_model_<version>.joblib.
"""
from __future__ import annotations

import argparse
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, classification_report, precision_recall_curve
from xgboost import XGBClassifier

from src.config import ROOT, REPORTS, SEED
from src.features.behavioural import FEATURE_COLUMNS
from src.features.online_features import ALL_FEATURE_COLUMNS, BASE_COLUMNS
from src.models.sparkov_data import get_sparkov_matrix
from src.models.sparkov_hybrid import ANOMALY_COLS

MODELS_DIR = ROOT / "models"


def train_production_model(version: str = "v1.0.0", sample_training: bool = False) -> Path:
    print(f"[{version}] Loading dataset and precomputed feature matrix...")
    X, y, df = get_sparkov_matrix()

    # Reorder columns to ensure strict match with ALL_FEATURE_COLUMNS
    for col in ALL_FEATURE_COLUMNS:
        if col not in X.columns:
            X[col] = 0.0
    X = X[ALL_FEATURE_COLUMNS].astype("float32")

    n = len(y)
    i, j = int(n * 0.70), int(n * 0.85)
    yv = y.to_numpy()

    Xtr, Xva, Xte = X.iloc[:i], X.iloc[i:j], X.iloc[j:]
    ytr, yva, yte = yv[:i], yv[i:j], yv[j:]

    print(f"[{version}] Chronological split: train={len(Xtr):,} val={len(Xva):,} test={len(Xte):,}")
    print(f"[{version}] Train fraud count = {int(ytr.sum()):,} ({ytr.mean():.4%})")

    spw = float((ytr == 0).sum() / max((ytr == 1).sum(), 1))
    print(f"[{version}] XGBoost scale_pos_weight = {spw:.2f}")

    # 1. Supervised XGBoost
    print(f"[{version}] Training Supervised XGBoost Classifier...")
    t0 = time.time()
    xgb_clf = XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=spw,
        tree_method="hist",
        eval_metric="aucpr",
        n_jobs=-1,
        random_state=SEED
    )
    xgb_clf.fit(Xtr, ytr)
    xgb_fit_time = time.time() - t0
    print(f"[{version}] XGBoost training completed in {xgb_fit_time:.1f}s")

    # 2. Unsupervised Isolation Forest (trained on legitimate cardholder behaviour only)
    print(f"[{version}] Training Unsupervised Isolation Forest...")
    t0 = time.time()
    legit_tr = Xtr[ytr == 0]
    fill_medians = legit_tr[ANOMALY_COLS].median().to_dict()
    sample_size = min(len(legit_tr), 200_000)
    legit_sample = legit_tr.sample(sample_size, random_state=SEED)[ANOMALY_COLS].fillna(fill_medians)
    
    iso_clf = IsolationForest(
        n_estimators=200,
        max_samples=256,
        random_state=SEED,
        n_jobs=-1
    )
    iso_clf.fit(legit_sample)
    iso_fit_time = time.time() - t0
    print(f"[{version}] Isolation Forest training completed in {iso_fit_time:.1f}s")

    # Compute validation & test scores
    print(f"[{version}] Evaluating on validation and test splits...")
    px_va = xgb_clf.predict_proba(Xva)[:, 1]
    px_te = xgb_clf.predict_proba(Xte)[:, 1]
    
    # Anomaly scores: normalized to [0, 1] range (higher = more abnormal)
    s_va_raw = -iso_clf.score_samples(Xva[ANOMALY_COLS].fillna(fill_medians))
    s_te_raw = -iso_clf.score_samples(Xte[ANOMALY_COLS].fillna(fill_medians))
    
    # Thresholds calculation
    prec, rec, thr = precision_recall_curve(yva, px_va)
    f1_scores = 2 * prec[:-1] * rec[:-1] / (prec[:-1] + rec[:-1] + 1e-12)
    optimal_f1_thr = float(thr[int(np.argmax(f1_scores))])
    
    # Block threshold (high precision, >= 0.80)
    block_thr = 0.80
    # Review threshold (balanced recall, max(0.15, optimal_f1_thr))
    review_thr = min(0.20, optimal_f1_thr)
    # Anomaly 99.5th percentile on validation
    anomaly_thr = float(np.percentile(s_va_raw, 99.5))

    # Test metrics
    test_pr_auc = float(average_precision_score(yte, px_te))
    pred_test = px_te >= review_thr
    tp = int(((pred_test == 1) & (yte == 1)).sum())
    fp = int(((pred_test == 1) & (yte == 0)).sum())
    fn = int(((pred_test == 0) & (yte == 1)).sum())
    tn = int(((pred_test == 0) & (yte == 0)).sum())
    test_prec = float(tp / max(tp + fp, 1))
    test_rec = float(tp / max(tp + fn, 1))
    test_f1 = float(2 * test_prec * test_rec / (test_prec + test_rec + 1e-12))

    print(f"[{version}] Test PR-AUC: {test_pr_auc:.4f} | Precision: {test_prec:.4f} | Recall: {test_rec:.4f} | F1: {test_f1:.4f}")

    # Compute reference statistics for explainability & drift
    print(f"[{version}] Computing reference feature distributions for SHAP and PSI...")
    ref_stats: Dict[str, Dict[str, float]] = {}
    ref_dists: Dict[str, list] = {}
    for col in ALL_FEATURE_COLUMNS:
        col_vals = legit_tr[col].dropna().to_numpy()
        ref_stats[col] = {
            "mean": float(np.mean(col_vals)),
            "std": float(np.std(col_vals)),
            "median": float(np.median(col_vals)),
            "min": float(np.min(col_vals)),
            "max": float(np.max(col_vals)),
        }
        # Subsample 2000 points for PSI reference distribution
        sub_idx = np.random.choice(len(col_vals), size=min(2000, len(col_vals)), replace=False)
        ref_dists[col] = col_vals[sub_idx].tolist()

    # Package model bundle
    bundle: Dict[str, Any] = {
        "model_version": version,
        "model_type": "hybrid_xgboost_isolation_forest",
        "dataset": "sparkov",
        "trained_at": datetime.utcnow().isoformat(),
        "xgb_model": xgb_clf,
        "iso_model": iso_clf,
        "feature_names": ALL_FEATURE_COLUMNS,
        "anomaly_cols": ANOMALY_COLS,
        "fill_medians": fill_medians,
        "thresholds": {
            "xgb_block_threshold": block_thr,
            "xgb_review_threshold": review_thr,
            "if_anomaly_threshold": anomaly_thr,
            "optimal_f1_threshold": optimal_f1_thr
        },
        "reference_stats": ref_stats,
        "reference_distributions": ref_dists,
        "metrics": {
            "test_pr_auc": round(test_pr_auc, 4),
            "test_precision": round(test_prec, 4),
            "test_recall": round(test_rec, 4),
            "test_f1": round(test_f1, 4),
            "train_rows": len(Xtr),
            "val_rows": len(Xva),
            "test_rows": len(Xte),
            "xgb_fit_seconds": round(xgb_fit_time, 1),
            "iso_fit_seconds": round(iso_fit_time, 1)
        }
    }

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    version_path = MODELS_DIR / f"production_model_{version}.joblib"
    latest_path = MODELS_DIR / "latest.joblib"

    joblib.dump(bundle, version_path, compress=3)
    joblib.dump(bundle, latest_path, compress=3)
    print(f"[{version}] Saved model bundle to {version_path} and {latest_path}")

    return version_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="v1.0.0")
    args = parser.parse_args()
    train_production_model(args.version)
