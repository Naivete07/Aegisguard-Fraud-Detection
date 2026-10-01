"""SHAP TreeExplainer and Unsupervised Feature Attribution (PRD FR-13, FR-14, FR-15).

Generates per-feature contribution charts and human-readable analyst explanations
for every flagged transaction (review or block).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import shap

# Human-readable labels and descriptions for feature names
FEATURE_METADATA = {
    "amt": {"label": "Transaction Amount", "unit": "$", "fmt": "${:.2f}"},
    "log_amt": {"label": "Log Amount", "unit": "", "fmt": "{:.2f}"},
    "amt_z": {"label": "Amount Z-Score (vs History)", "unit": "σ", "fmt": "{:+.1f}σ"},
    "amt_over_card_mean": {"label": "Amount / Historical Average", "unit": "x", "fmt": "{:.1f}x"},
    "dist_home_km": {"label": "Distance from Cardholder Home", "unit": "km", "fmt": "{:.1f} km"},
    "dist_prev_km": {"label": "Distance from Previous Transaction", "unit": "km", "fmt": "{:.1f} km"},
    "speed_kmh": {"label": "Implied Travel Speed", "unit": "km/h", "fmt": "{:.1f} km/h"},
    "secs_since_last": {"label": "Time Since Last Transaction", "unit": "s", "fmt": "{:.0f}s"},
    "n_prev_txn": {"label": "Total Previous Transactions", "unit": "", "fmt": "{:.0f}"},
    "txn_count_1h": {"label": "1-Hour Transaction Count", "unit": "txns", "fmt": "{:.0f} txns"},
    "txn_count_24h": {"label": "24-Hour Transaction Count", "unit": "txns", "fmt": "{:.0f} txns"},
    "txn_count_7d": {"label": "7-Day Transaction Count", "unit": "txns", "fmt": "{:.0f} txns"},
    "amt_sum_1h": {"label": "1-Hour Spending Velocity", "unit": "$", "fmt": "${:.2f}"},
    "amt_sum_24h": {"label": "24-Hour Spending Velocity", "unit": "$", "fmt": "${:.2f}"},
    "amt_sum_7d": {"label": "7-Day Spending Velocity", "unit": "$", "fmt": "${:.2f}"},
    "is_night": {"label": "Late Night / Early Morning", "unit": "", "fmt": "{:.0f}"},
    "hour": {"label": "Hour of Day", "unit": "h", "fmt": "{:.0f}:00"},
    "dow": {"label": "Day of Week", "unit": "", "fmt": "{:.0f}"},
    "age": {"label": "Cardholder Age", "unit": "yrs", "fmt": "{:.0f} yrs"},
    "city_pop": {"label": "City Population", "unit": "", "fmt": "{:,.0f}"},
    "category": {"label": "Merchant Category", "unit": "", "fmt": "{:.0f}"},
    "gender": {"label": "Gender", "unit": "", "fmt": "{:.0f}"},
    "is_new_category": {"label": "New Category for Card", "unit": "", "fmt": "{:.0f}"},
    "is_new_merchant": {"label": "New Merchant for Card", "unit": "", "fmt": "{:.0f}"},
}


class FraudExplainer:
    """Computes SHAP values and generates plain-language explanations."""

    def __init__(
        self,
        xgb_model: Any,
        feature_names: List[str],
        reference_stats: Optional[Dict[str, Dict[str, float]]] = None
    ):
        self.xgb_model = xgb_model
        self.feature_names = feature_names
        self.reference_stats = reference_stats or {}
        self.tree_explainer = shap.TreeExplainer(xgb_model)

    def explain(
        self,
        features_df: pd.DataFrame,
        is_unsupervised_only: bool = False,
        top_n: int = 6
    ) -> Dict[str, Any]:
        """Generate full explanation payload for a single transaction row.
        
        Returns a rich dictionary with:
            - base_value: expected model margin / log-odds
            - top_positive_drivers: features increasing fraud risk
            - top_negative_drivers: features decreasing fraud risk
            - all_contributions: complete list of SHAP contributions
            - summary_narrative: synthesized human explanation
            - unsupervised_deviations: anomalous feature deviations
        """
        # Ensure correct column ordering
        df = features_df[self.feature_names].astype("float32")
        
        # Fast exact C++ TreeSHAP via XGBoost booster
        try:
            import xgboost as xgb
            booster = self.xgb_model.get_booster()
            dmat = xgb.DMatrix(df, feature_names=self.feature_names)
            contribs = booster.predict(dmat, pred_contribs=True)[0]
            shap_vals = contribs[:-1]
            base_val = float(contribs[-1])
        except Exception:
            # Fallback to python shap package
            raw_shap = self.tree_explainer.shap_values(df)
            if isinstance(raw_shap, list):
                shap_vals = raw_shap[1][0]
            elif len(raw_shap.shape) == 2:
                shap_vals = raw_shap[0]
            else:
                shap_vals = raw_shap
            base_val = float(
                self.tree_explainer.expected_value[1]
                if isinstance(self.tree_explainer.expected_value, (list, np.ndarray))
                else self.tree_explainer.expected_value
            )

        contributions: List[Dict[str, Any]] = []
        for feat_name, s_val in zip(self.feature_names, shap_vals):
            feat_val = float(df[feat_name].iloc[0])
            meta = FEATURE_METADATA.get(feat_name, {"label": feat_name, "unit": "", "fmt": "{:.2f}"})
            
            try:
                formatted_val = meta["fmt"].format(feat_val)
            except Exception:
                formatted_val = str(feat_val)

            contributions.append({
                "feature": feat_name,
                "label": meta["label"],
                "value": feat_val,
                "formatted_value": formatted_val,
                "shap_value": round(float(s_val), 4),
                "impact": "INCREASES_RISK" if s_val > 0 else "DECREASES_RISK"
            })

        # Sort contributions by absolute SHAP magnitude
        sorted_by_abs = sorted(contributions, key=lambda x: abs(x["shap_value"]), reverse=True)
        positive_drivers = [c for c in sorted_by_abs if c["shap_value"] > 0][:top_n]
        negative_drivers = [c for c in sorted_by_abs if c["shap_value"] < 0][:top_n]

        # Calculate Unsupervised Deviations against reference distribution
        unsupervised_devs = []
        if self.reference_stats:
            for feat_name in self.feature_names:
                if feat_name in self.reference_stats:
                    ref = self.reference_stats[feat_name]
                    mean = ref.get("mean", 0.0)
                    std = ref.get("std", 1.0)
                    val = float(df[feat_name].iloc[0])
                    if std > 1e-6:
                        z_dev = (val - mean) / std
                        if abs(z_dev) >= 2.0:
                            meta = FEATURE_METADATA.get(feat_name, {"label": feat_name, "unit": "", "fmt": "{:.2f}"})
                            unsupervised_devs.append({
                                "feature": feat_name,
                                "label": meta["label"],
                                "value": val,
                                "formatted_value": meta["fmt"].format(val) if "{:" in meta["fmt"] else str(val),
                                "z_score": round(float(z_dev), 2),
                                "ref_mean": round(float(mean), 2),
                                "ref_std": round(float(std), 2),
                            })
            unsupervised_devs.sort(key=lambda x: abs(x["z_score"]), reverse=True)

        # Synthesize analyst narrative
        narrative = self._generate_narrative(
            positive_drivers,
            unsupervised_devs,
            is_unsupervised_only
        )

        return {
            "base_value": round(base_val, 4),
            "top_positive_drivers": positive_drivers,
            "top_negative_drivers": negative_drivers,
            "all_contributions": sorted_by_abs,
            "unsupervised_deviations": unsupervised_devs[:5],
            "summary_narrative": narrative
        }

    def _generate_narrative(
        self,
        pos_drivers: List[Dict[str, Any]],
        unsupervised_devs: List[Dict[str, Any]],
        is_unsupervised_only: bool
    ) -> str:
        """Create a clear 1-2 sentence executive explanation for the analyst."""
        if is_unsupervised_only or (not pos_drivers and unsupervised_devs):
            dev_phrases = [
                f"{d['label']} is abnormal ({d['formatted_value']} vs baseline {d['ref_mean']})"
                for d in unsupervised_devs[:2]
            ]
            if dev_phrases:
                return f"Anomaly detector flagged unusual pattern: {', '.join(dev_phrases)}."
            return "Flagged due to multi-dimensional behavioural divergence from historical cardholder profile."

        reasons = []
        for d in pos_drivers[:3]:
            f = d["feature"]
            val_str = d["formatted_value"]
            if f == "amt" or f == "log_amt":
                reasons.append(f"high transaction amount ({val_str})")
            elif f == "amt_z":
                reasons.append(f"spending spike ({val_str} above normal)")
            elif f == "dist_home_km":
                reasons.append(f"distant location ({val_str} from home)")
            elif f == "speed_kmh":
                reasons.append(f"rapid travel speed ({val_str})")
            elif f == "txn_count_1h" or f == "txn_count_24h":
                reasons.append(f"high velocity ({val_str})")
            elif f == "is_night":
                reasons.append("unusual late-night transaction time")
            elif f == "is_new_merchant":
                reasons.append("first-time transaction at this merchant")
            else:
                reasons.append(f"{d['label'].lower()} ({val_str})")

        if reasons:
            return f"Alert triggered primarily by {', '.join(reasons)}."
        return "Transaction score elevated across combined behavioural risk factors."
