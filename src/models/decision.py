"""3-Tier Decision Engine: Approve / Review / Block.

Combines supervised XGBoost risk probability and unsupervised anomaly score
with cost-sensitive thresholding and analyst triage prioritization (PRD FR-10).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass
class DecisionThresholds:
    """Configurable decision boundaries."""
    xgb_block_threshold: float = 0.80      # High probability -> immediate block
    xgb_review_threshold: float = 0.20     # Moderate risk -> manual analyst review
    if_anomaly_threshold: float = 0.65     # High anomaly score -> manual analyst review
    cost_fp: float = 15.0                  # Cost of false positive (analyst review + cardholder friction)


@dataclass
class DecisionResult:
    decision: str                          # 'approve' | 'review' | 'block'
    risk_band: str                         # 'HIGH' | 'MEDIUM' | 'LOW'
    is_alert: bool                         # True if review or block
    risk_score: float                      # Supervised XGBoost probability [0.0, 1.0]
    anomaly_score: float                   # Unsupervised anomaly score [0.0, 1.0]
    trigger_reason: str                    # Human-readable trigger explanation
    recommended_action: str                # Action guidance for analyst


class DecisionEngine:
    """Evaluates transaction scores against tier boundaries."""

    def __init__(self, thresholds: Optional[DecisionThresholds] = None):
        self.thresholds = thresholds or DecisionThresholds()

    def evaluate(
        self,
        risk_score: float,
        anomaly_score: float,
        amount: float = 0.0
    ) -> DecisionResult:
        """Evaluate risk and anomaly scores into approve/review/block decision."""
        th = self.thresholds
        
        # 1. Block tier: High confidence supervised fraud
        if risk_score >= th.xgb_block_threshold:
            return DecisionResult(
                decision="block",
                risk_band="HIGH",
                is_alert=True,
                risk_score=float(risk_score),
                anomaly_score=float(anomaly_score),
                trigger_reason=f"Supervised fraud probability ({risk_score:.1%}) exceeds block threshold ({th.xgb_block_threshold:.1%}).",
                recommended_action="Decline transaction immediately and freeze card pending cardholder verification."
            )
        
        # 2. Review tier: Mid-range supervised probability OR high unsupervised anomaly
        xgb_review_flag = risk_score >= th.xgb_review_threshold
        if_review_flag = anomaly_score >= th.if_anomaly_threshold

        if xgb_review_flag or if_review_flag:
            if xgb_review_flag and if_review_flag:
                reason = f"Dual trigger: elevated fraud probability ({risk_score:.1%}) and high statistical anomaly score ({anomaly_score:.1%})."
                band = "HIGH"
            elif xgb_review_flag:
                reason = f"Elevated supervised fraud probability ({risk_score:.1%}) requires manual verification."
                band = "MEDIUM"
            else:
                reason = f"Unsupervised anomaly detected ({anomaly_score:.1%}): transaction deviates sharply from cardholder pattern."
                band = "MEDIUM"

            return DecisionResult(
                decision="review",
                risk_band=band,
                is_alert=True,
                risk_score=float(risk_score),
                anomaly_score=float(anomaly_score),
                trigger_reason=reason,
                recommended_action="Route to analyst review queue. Check SHAP feature breakdown and cardholder velocity."
            )

        # 3. Approve tier: Low risk & normal behavior
        return DecisionResult(
            decision="approve",
            risk_band="LOW",
            is_alert=False,
            risk_score=float(risk_score),
            anomaly_score=float(anomaly_score),
            trigger_reason="Transaction within normal behavioural boundaries.",
            recommended_action="Approve transaction inline."
        )
