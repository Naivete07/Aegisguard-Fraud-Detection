"""Feature drift and Population Stability Index (PSI) monitoring (PRD FR-22)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def calculate_psi(
    expected: np.ndarray,
    actual: np.ndarray,
    num_buckets: int = 10
) -> Tuple[float, List[Dict[str, Any]]]:
    """Calculate Population Stability Index (PSI) between reference and recent samples."""
    exp = np.asarray(expected, dtype=float)
    act = np.asarray(actual, dtype=float)
    exp = exp[~np.isnan(exp)]
    act = act[~np.isnan(act)]

    if len(exp) < 10 or len(act) < 10:
        return 0.0, []

    # Determine quantile bins based on reference distribution
    percentiles = np.linspace(0, 100, num_buckets + 1)
    bins = np.percentile(exp, percentiles)
    bins[0] = -np.inf
    bins[-1] = np.inf
    bins = np.unique(bins)

    if len(bins) < 2:
        return 0.0, []

    # Calculate counts in each bucket
    exp_counts, _ = np.histogram(exp, bins=bins)
    act_counts, _ = np.histogram(act, bins=bins)

    # Convert to proportions with epsilon smoothing
    eps = 1e-4
    exp_pct = (exp_counts / len(exp)) + eps
    act_pct = (act_counts / len(act)) + eps
    exp_pct /= exp_pct.sum()
    act_pct /= act_pct.sum()

    # PSI calculation
    psi_values = (act_pct - exp_pct) * np.log(act_pct / exp_pct)
    total_psi = float(np.sum(psi_values))

    bucket_details = []
    for i in range(len(exp_counts)):
        low_bound = bins[i] if bins[i] != -np.inf else float(np.min(exp))
        high_bound = bins[i + 1] if bins[i + 1] != np.inf else float(np.max(exp))
        bucket_details.append({
            "bucket_idx": i,
            "min_val": round(float(low_bound), 2),
            "max_val": round(float(high_bound), 2),
            "expected_pct": round(float(exp_pct[i]), 4),
            "actual_pct": round(float(act_pct[i]), 4),
            "bucket_psi": round(float(psi_values[i]), 4)
        })

    return round(total_psi, 4), bucket_details


class DriftDetector:
    """Tracks feature drift against baseline training distributions."""

    def __init__(self, reference_distributions: Optional[Dict[str, List[float]]] = None):
        self.reference_distributions = reference_distributions or {}

    def evaluate_drift(
        self,
        recent_features: pd.DataFrame,
        features_to_check: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Evaluate PSI drift across key numerical and behavioral features."""
        cols = features_to_check or ["amt", "dist_home_km", "speed_kmh", "amt_z", "txn_count_24h", "hour"]
        results = {}
        max_psi = 0.0
        drifted_features = []

        for col in cols:
            if col not in recent_features.columns or col not in self.reference_distributions:
                continue
            
            exp_vals = np.array(self.reference_distributions[col])
            act_vals = recent_features[col].dropna().to_numpy()

            psi, buckets = calculate_psi(exp_vals, act_vals)
            
            if psi >= 0.25:
                status = "SIGNIFICANT_DRIFT"
                drifted_features.append(col)
            elif psi >= 0.10:
                status = "MODERATE_DRIFT"
            else:
                status = "STABLE"

            max_psi = max(max_psi, psi)
            results[col] = {
                "psi": psi,
                "status": status,
                "buckets": buckets
            }

        overall_status = "SIGNIFICANT_DRIFT" if max_psi >= 0.25 else ("MODERATE_DRIFT" if max_psi >= 0.10 else "STABLE")

        return {
            "overall_status": overall_status,
            "max_psi": round(max_psi, 4),
            "drifted_features": drifted_features,
            "sample_size": len(recent_features),
            "feature_metrics": results
        }
