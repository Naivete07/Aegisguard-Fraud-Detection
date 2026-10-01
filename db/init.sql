-- Core schema from the PRD data model (indicative; extended in Sprint 3)
CREATE TABLE IF NOT EXISTS ml_models (
    model_version TEXT PRIMARY KEY,
    model_type    TEXT NOT NULL,
    dataset       TEXT,
    trained_at    TIMESTAMPTZ DEFAULT now(),
    metrics_json  JSONB,
    artefact_path TEXT
);

CREATE TABLE IF NOT EXISTS transactions (
    txn_id        TEXT PRIMARY KEY,          -- unique => idempotent writes (ON CONFLICT DO NOTHING)
    card_id       TEXT NOT NULL,
    merchant_id   TEXT,
    amount        NUMERIC(14,2) NOT NULL,
    txn_time      TIMESTAMPTZ NOT NULL,
    channel       TEXT,
    lat           DOUBLE PRECISION,
    long          DOUBLE PRECISION,
    features_json JSONB,
    risk_score    DOUBLE PRECISION,
    anomaly_score DOUBLE PRECISION,
    decision      TEXT CHECK (decision IN ('approve','review','block')),
    model_version TEXT REFERENCES ml_models(model_version),
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fraud_alerts (
    alert_id      BIGSERIAL PRIMARY KEY,
    txn_id        TEXT UNIQUE NOT NULL REFERENCES transactions(txn_id),
    status        TEXT NOT NULL DEFAULT 'open',   -- open | confirmed_fraud | false_positive
    risk_band     TEXT,
    shap_json     JSONB,
    model_version TEXT REFERENCES ml_models(model_version),
    analyst_id    TEXT,
    resolved_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_log (
    log_id      BIGSERIAL PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    action      TEXT NOT NULL,
    actor       TEXT,
    ts          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_txn_card_time ON transactions (card_id, txn_time);
CREATE INDEX IF NOT EXISTS idx_alert_status ON fraud_alerts (status);
