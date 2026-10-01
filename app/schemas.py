"""Pydantic schemas for request and response validation (PRD NFR-7, Table 1)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TransactionRequest(BaseModel):
    """Transaction scoring payload."""
    txn_id: Optional[str] = Field(default=None, description="Unique transaction ID (generated if empty)")
    cc_num: Optional[str] = Field(default=None, description="Credit card number / card ID")
    card_id: Optional[str] = Field(default=None, description="Alias for cc_num")
    amt: Optional[float] = Field(default=None, description="Transaction amount")
    amount: Optional[float] = Field(default=None, description="Alias for amt")
    trans_date_trans_time: Optional[str] = Field(default=None, description="Transaction timestamp (ISO/string)")
    txn_time: Optional[str] = Field(default=None, description="Alias for trans_date_trans_time")
    merchant: Optional[str] = Field(default="unknown_merchant", description="Merchant name or ID")
    category: Optional[str] = Field(default="misc_pos", description="Merchant category")
    lat: Optional[float] = Field(default=35.0, description="Cardholder home latitude")
    long: Optional[float] = Field(default=-90.0, description="Cardholder home longitude")
    lon: Optional[float] = Field(default=None, description="Alias for long")
    merch_lat: Optional[float] = Field(default=35.0, description="Merchant terminal latitude")
    merch_long: Optional[float] = Field(default=-90.0, description="Merchant terminal longitude")
    city_pop: Optional[float] = Field(default=10000.0, description="Cardholder city population")
    dob: Optional[str] = Field(default="1985-01-01", description="Cardholder date of birth")
    age: Optional[float] = Field(default=40.0, description="Cardholder age")
    gender: Optional[str] = Field(default="M", description="Cardholder gender (M/F)")
    channel: Optional[str] = Field(default="POS", description="Channel: POS, WEB, APP")

    def get_card_id(self) -> str:
        return str(self.cc_num or self.card_id or "card_unknown")

    def get_amount(self) -> float:
        return float(self.amt if self.amt is not None else (self.amount if self.amount is not None else 0.0))

    def get_timestamp(self) -> str:
        return str(self.trans_date_trans_time or self.txn_time or datetime.utcnow().isoformat())


class ScoreResponse(BaseModel):
    """Synchronous scoring response."""
    txn_id: str
    decision: str = Field(description="approve | review | block")
    risk_score: float = Field(description="Supervised XGBoost fraud probability [0, 1]")
    anomaly_score: float = Field(description="Unsupervised Isolation Forest score [0, 1]")
    risk_band: str = Field(description="HIGH | MEDIUM | LOW")
    is_alert: bool
    alert_id: Optional[int] = None
    model_version: str
    trigger_reason: str
    recommended_action: str
    latency_ms: float
    features: Optional[Dict[str, Any]] = None


class AlertSummaryItem(BaseModel):
    alert_id: int
    txn_id: str
    card_id: str
    merchant_id: Optional[str] = None
    amount: float
    txn_time: str
    channel: Optional[str] = None
    status: str
    risk_band: str
    decision: str
    risk_score: float
    anomaly_score: float
    model_version: Optional[str] = None
    analyst_id: Optional[str] = None
    created_at: str


class AlertListResponse(BaseModel):
    total: int
    alerts: List[AlertSummaryItem]
    limit: int
    offset: int


class AlertDetailResponse(BaseModel):
    alert_id: int
    txn_id: str
    status: str
    risk_band: str
    decision: str
    risk_score: float
    anomaly_score: float
    model_version: Optional[str] = None
    analyst_id: Optional[str] = None
    resolution_notes: Optional[str] = None
    resolved_at: Optional[str] = None
    created_at: str
    card_id: str
    merchant_id: Optional[str] = None
    amount: float
    txn_time: str
    channel: Optional[str] = None
    lat: Optional[float] = None
    long: Optional[float] = None
    features_json: Optional[Dict[str, Any]] = None
    shap_json: Optional[Dict[str, Any]] = None


class AlertResolutionRequest(BaseModel):
    """Analyst resolution payload (PATCH /alerts/{id})."""
    status: str = Field(description="confirmed_fraud | false_positive")
    analyst_id: str = Field(default="analyst_1", description="Identifier of the resolving analyst")
    notes: Optional[str] = Field(default="", description="Optional resolution rationale notes")


class RetrainRequest(BaseModel):
    """Trigger model retraining."""
    version_tag: Optional[str] = Field(default=None, description="Tag for new model version")
    include_analyst_labels: bool = Field(default=True, description="Incorporate analyst feedback labels")


class RetrainResponse(BaseModel):
    status: str
    model_version: str
    metrics: Dict[str, Any]
    trained_at: str


class SummaryStatsResponse(BaseModel):
    """System KPI summary (PRD FR-21)."""
    total_transactions: int
    total_volume_usd: float
    total_alerts: int
    open_alerts: int
    confirmed_fraud: int
    false_positives: int
    blocked_count: int
    review_count: int
    false_positive_rate: float
    prevented_fraud_usd: float


class HealthResponse(BaseModel):
    status: str
    api: str
    database: str
    redis: str
    active_model_version: str
    uptime_seconds: float
