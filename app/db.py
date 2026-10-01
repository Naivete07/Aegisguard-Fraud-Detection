"""Database access layer with PostgreSQL and SQLite automatic fallback.

Enforces idempotent writes (PRD FR-2) and full audit logging (PRD FR-17).
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.config import ROOT

DB_PATH = ROOT / "data" / "fraud.db"


class Database:
    """Manages database connections, schemas, and queries."""

    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or os.environ.get("DATABASE_URL")
        self.is_postgres = False
        self._test_connection()
        self._init_schema()

    def _test_connection(self) -> None:
        if self.db_url and "postgres" in self.db_url:
            try:
                import psycopg
                with psycopg.connect(self.db_url, connect_timeout=2) as conn:
                    conn.execute("SELECT 1")
                self.is_postgres = True
                print("[Database] Connected to PostgreSQL successfully.")
                return
            except Exception as e:
                print(f"[Database] PostgreSQL not accessible ({e}), falling back to SQLite at {DB_PATH}")
        self.is_postgres = False

    @contextmanager
    def get_conn(self):
        if self.is_postgres:
            import psycopg
            from psycopg.rows import dict_row
            conn = psycopg.connect(self.db_url, row_factory=dict_row)
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        else:
            import threading
            if not hasattr(self, "_tls"):
                self._tls = threading.local()
            if not hasattr(self._tls, "conn") or self._tls.conn is None:
                DB_PATH.parent.mkdir(parents=True, exist_ok=True)
                c = sqlite3.connect(str(DB_PATH), timeout=30.0, check_same_thread=False)
                c.row_factory = sqlite3.Row
                c.execute("PRAGMA journal_mode=WAL;")
                c.execute("PRAGMA synchronous=NORMAL;")
                c.execute("PRAGMA busy_timeout=10000;")
                self._tls.conn = c
            conn = self._tls.conn
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def _init_schema(self) -> None:
        with self.get_conn() as conn:
            if self.is_postgres:
                conn.execute("""
                CREATE TABLE IF NOT EXISTS ml_models (
                    model_version TEXT PRIMARY KEY,
                    model_type    TEXT NOT NULL,
                    dataset       TEXT,
                    trained_at    TIMESTAMPTZ DEFAULT now(),
                    metrics_json  JSONB,
                    artefact_path TEXT
                );
                CREATE TABLE IF NOT EXISTS transactions (
                    txn_id        TEXT PRIMARY KEY,
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
                    model_version TEXT,
                    created_at    TIMESTAMPTZ DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS fraud_alerts (
                    alert_id      BIGSERIAL PRIMARY KEY,
                    txn_id        TEXT UNIQUE NOT NULL REFERENCES transactions(txn_id),
                    status        TEXT NOT NULL DEFAULT 'open',
                    risk_band     TEXT,
                    decision      TEXT,
                    shap_json     JSONB,
                    model_version TEXT,
                    analyst_id    TEXT,
                    resolution_notes TEXT,
                    resolved_at   TIMESTAMPTZ,
                    created_at    TIMESTAMPTZ DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    log_id      BIGSERIAL PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    entity_id   TEXT NOT NULL,
                    action      TEXT NOT NULL,
                    actor       TEXT,
                    details     TEXT,
                    ts          TIMESTAMPTZ DEFAULT now()
                );
                CREATE INDEX IF NOT EXISTS idx_txn_card_time ON transactions (card_id, txn_time);
                CREATE INDEX IF NOT EXISTS idx_alert_status ON fraud_alerts (status);
                """)
            else:
                conn.executescript("""
                CREATE TABLE IF NOT EXISTS ml_models (
                    model_version TEXT PRIMARY KEY,
                    model_type    TEXT NOT NULL,
                    dataset       TEXT,
                    trained_at    TEXT,
                    metrics_json  TEXT,
                    artefact_path TEXT
                );
                CREATE TABLE IF NOT EXISTS transactions (
                    txn_id        TEXT PRIMARY KEY,
                    card_id       TEXT NOT NULL,
                    merchant_id   TEXT,
                    amount        REAL NOT NULL,
                    txn_time      TEXT NOT NULL,
                    channel       TEXT,
                    lat           REAL,
                    long          REAL,
                    features_json TEXT,
                    risk_score    REAL,
                    anomaly_score REAL,
                    decision      TEXT,
                    model_version TEXT,
                    created_at    TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS fraud_alerts (
                    alert_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    txn_id        TEXT UNIQUE NOT NULL,
                    status        TEXT NOT NULL DEFAULT 'open',
                    risk_band     TEXT,
                    decision      TEXT,
                    shap_json     TEXT,
                    model_version TEXT,
                    analyst_id    TEXT,
                    resolution_notes TEXT,
                    resolved_at   TEXT,
                    created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(txn_id) REFERENCES transactions(txn_id)
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    entity_id   TEXT NOT NULL,
                    action      TEXT NOT NULL,
                    actor       TEXT,
                    details     TEXT,
                    ts          TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_txn_card_time ON transactions (card_id, txn_time);
                CREATE INDEX IF NOT EXISTS idx_alert_status ON fraud_alerts (status);
                """)

    def save_transaction(
        self,
        txn_id: str,
        card_id: str,
        merchant_id: str,
        amount: float,
        txn_time: str,
        channel: str,
        lat: float,
        lon: float,
        features_dict: Dict[str, Any],
        risk_score: float,
        anomaly_score: float,
        decision: str,
        model_version: str
    ) -> bool:
        """Idempotent insert of transaction (PRD FR-2)."""
        feat_str = json.dumps(features_dict)
        with self.get_conn() as conn:
            if self.is_postgres:
                query = """
                INSERT INTO transactions (
                    txn_id, card_id, merchant_id, amount, txn_time, channel,
                    lat, long, features_json, risk_score, anomaly_score, decision, model_version
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (txn_id) DO NOTHING
                """
                res = conn.execute(query, (
                    txn_id, card_id, merchant_id, amount, txn_time, channel,
                    lat, lon, feat_str, risk_score, anomaly_score, decision, model_version
                ))
                return True
            else:
                query = """
                INSERT OR IGNORE INTO transactions (
                    txn_id, card_id, merchant_id, amount, txn_time, channel,
                    lat, long, features_json, risk_score, anomaly_score, decision, model_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                conn.execute(query, (
                    txn_id, card_id, merchant_id, amount, txn_time, channel,
                    lat, lon, feat_str, risk_score, anomaly_score, decision, model_version
                ))
                return True

    def create_alert(
        self,
        txn_id: str,
        risk_band: str,
        decision: str,
        model_version: str,
        shap_dict: Optional[Dict[str, Any]] = None
    ) -> Optional[int]:
        """Create alert for review or block tier."""
        shap_str = json.dumps(shap_dict) if shap_dict else None
        with self.get_conn() as conn:
            if self.is_postgres:
                query = """
                INSERT INTO fraud_alerts (txn_id, status, risk_band, decision, shap_json, model_version)
                VALUES (%s, 'open', %s, %s, %s, %s)
                ON CONFLICT (txn_id) DO NOTHING
                RETURNING alert_id
                """
                cur = conn.execute(query, (txn_id, risk_band, decision, shap_str, model_version))
                row = cur.fetchone()
                alert_id = row["alert_id"] if row else None
            else:
                query = """
                INSERT OR IGNORE INTO fraud_alerts (txn_id, status, risk_band, decision, shap_json, model_version)
                VALUES (?, 'open', ?, ?, ?, ?)
                """
                cur = conn.execute(query, (txn_id, risk_band, decision, shap_str, model_version))
                alert_id = cur.lastrowid

            if alert_id:
                self.log_audit(
                    conn=conn,
                    entity_type="fraud_alert",
                    entity_id=str(alert_id),
                    action="ALERT_TRIGGERED",
                    actor="scoring_engine",
                    details=f"Decision: {decision}, Risk Band: {risk_band}"
                )
            return alert_id

    def update_alert_shap(self, txn_id: str, shap_dict: Dict[str, Any]) -> None:
        """Update SHAP explanation asynchronously."""
        shap_str = json.dumps(shap_dict)
        with self.get_conn() as conn:
            if self.is_postgres:
                conn.execute("UPDATE fraud_alerts SET shap_json = %s WHERE txn_id = %s", (shap_str, txn_id))
            else:
                conn.execute("UPDATE fraud_alerts SET shap_json = ? WHERE txn_id = ?", (shap_str, txn_id))

    def get_alerts(
        self,
        status: Optional[str] = None,
        decision: Optional[str] = None,
        risk_band: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_order: str = "DESC"
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Fetch filtered and paginated alerts."""
        allowed_sorts = {"created_at", "risk_score", "amount", "txn_time"}
        col = sort_by if sort_by in allowed_sorts else "created_at"
        order = "DESC" if sort_order.upper() == "DESC" else "ASC"

        where_clauses = []
        params: List[Any] = []

        if status and status.lower() != "all":
            where_clauses.append("a.status = %s" if self.is_postgres else "a.status = ?")
            params.append(status.lower())

        if decision and decision.lower() != "all":
            where_clauses.append("a.decision = %s" if self.is_postgres else "a.decision = ?")
            params.append(decision.lower())

        if risk_band and risk_band.lower() != "all":
            where_clauses.append("a.risk_band = %s" if self.is_postgres else "a.risk_band = ?")
            params.append(risk_band.upper())

        if search:
            s_param = f"%{search}%"
            where_clauses.append("(t.card_id LIKE %s OR t.merchant_id LIKE %s OR t.txn_id LIKE %s)" if self.is_postgres else "(t.card_id LIKE ? OR t.merchant_id LIKE ? OR t.txn_id LIKE ?)")
            params.extend([s_param, s_param, s_param])

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        with self.get_conn() as conn:
            count_query = f"""
            SELECT COUNT(*) as total
            FROM fraud_alerts a
            JOIN transactions t ON a.txn_id = t.txn_id
            {where_sql}
            """
            cur = conn.execute(count_query, params)
            total = cur.fetchone()["total"]

            order_target = f"t.{col}" if col in {"amount", "risk_score", "txn_time"} else f"a.{col}"
            
            data_query = f"""
            SELECT 
                a.alert_id, a.txn_id, a.status, a.risk_band, a.decision,
                a.model_version, a.analyst_id, a.resolution_notes, a.resolved_at, a.created_at,
                t.card_id, t.merchant_id, t.amount, t.txn_time, t.channel,
                t.risk_score, t.anomaly_score
            FROM fraud_alerts a
            JOIN transactions t ON a.txn_id = t.txn_id
            {where_sql}
            ORDER BY {order_target} {order}
            LIMIT {limit} OFFSET {offset}
            """
            cur = conn.execute(data_query, params)
            rows = [dict(r) for r in cur.fetchall()]

            return rows, total

    def get_alert_detail(self, alert_id: int) -> Optional[Dict[str, Any]]:
        """Fetch complete alert details including full SHAP JSON."""
        with self.get_conn() as conn:
            query = """
            SELECT 
                a.alert_id, a.txn_id, a.status, a.risk_band, a.decision, a.shap_json,
                a.model_version, a.analyst_id, a.resolution_notes, a.resolved_at, a.created_at,
                t.card_id, t.merchant_id, t.amount, t.txn_time, t.channel, t.lat, t.long,
                t.features_json, t.risk_score, t.anomaly_score
            FROM fraud_alerts a
            JOIN transactions t ON a.txn_id = t.txn_id
            WHERE a.alert_id = %s
            """ if self.is_postgres else """
            SELECT 
                a.alert_id, a.txn_id, a.status, a.risk_band, a.decision, a.shap_json,
                a.model_version, a.analyst_id, a.resolution_notes, a.resolved_at, a.created_at,
                t.card_id, t.merchant_id, t.amount, t.txn_time, t.channel, t.lat, t.long,
                t.features_json, t.risk_score, t.anomaly_score
            FROM fraud_alerts a
            JOIN transactions t ON a.txn_id = t.txn_id
            WHERE a.alert_id = ?
            """
            cur = conn.execute(query, (alert_id,))
            row = cur.fetchone()
            if not row:
                return None
            res = dict(row)
            if isinstance(res.get("shap_json"), str):
                try:
                    res["shap_json"] = json.loads(res["shap_json"])
                except Exception:
                    pass
            if isinstance(res.get("features_json"), str):
                try:
                    res["features_json"] = json.loads(res["features_json"])
                except Exception:
                    pass
            return res

    def resolve_alert(
        self,
        alert_id: int,
        status: str,
        analyst_id: str,
        notes: str = ""
    ) -> bool:
        """Resolve alert with analyst label and write audit log (PRD FR-20)."""
        now = datetime.utcnow().isoformat()
        with self.get_conn() as conn:
            query = """
            UPDATE fraud_alerts
            SET status = %s, analyst_id = %s, resolution_notes = %s, resolved_at = %s
            WHERE alert_id = %s
            """ if self.is_postgres else """
            UPDATE fraud_alerts
            SET status = ?, analyst_id = ?, resolution_notes = ?, resolved_at = ?
            WHERE alert_id = ?
            """
            conn.execute(query, (status, analyst_id, notes, now, alert_id))
            
            self.log_audit(
                conn=conn,
                entity_type="fraud_alert",
                entity_id=str(alert_id),
                action=f"ALERT_RESOLVED_{status.upper()}",
                actor=analyst_id,
                details=f"Status: {status}, Notes: {notes}"
            )
            return True

    def log_audit(
        self,
        conn: Any,
        entity_type: str,
        entity_id: str,
        action: str,
        actor: Optional[str] = "system",
        details: Optional[str] = None
    ) -> None:
        """Record audit event (PRD FR-17)."""
        query = """
        INSERT INTO audit_log (entity_type, entity_id, action, actor, details)
        VALUES (%s, %s, %s, %s, %s)
        """ if self.is_postgres else """
        INSERT INTO audit_log (entity_type, entity_id, action, actor, details)
        VALUES (?, ?, ?, ?, ?)
        """
        conn.execute(query, (entity_type, entity_id, action, actor or "system", details or ""))

    def get_summary_stats(self) -> Dict[str, Any]:
        """Aggregate system KPIs for summary panel (PRD FR-21)."""
        with self.get_conn() as conn:
            cur = conn.execute("SELECT COUNT(*) as total_txns, COALESCE(SUM(amount), 0) as total_vol FROM transactions")
            txn_stat = cur.fetchone()
            
            cur = conn.execute("""
            SELECT 
                COUNT(*) as total_alerts,
                SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_alerts,
                SUM(CASE WHEN status = 'confirmed_fraud' THEN 1 ELSE 0 END) as confirmed_fraud,
                SUM(CASE WHEN status = 'false_positive' THEN 1 ELSE 0 END) as false_positives,
                SUM(CASE WHEN decision = 'block' THEN 1 ELSE 0 END) as blocked_count,
                SUM(CASE WHEN decision = 'review' THEN 1 ELSE 0 END) as review_count
            FROM fraud_alerts
            """)
            alert_stat = cur.fetchone()

            # Prevented fraud amount
            cur = conn.execute("""
            SELECT COALESCE(SUM(t.amount), 0) as prevented_fraud_amt
            FROM fraud_alerts a
            JOIN transactions t ON a.txn_id = t.txn_id
            WHERE a.status = 'confirmed_fraud' OR a.decision = 'block'
            """)
            prevented = cur.fetchone()["prevented_fraud_amt"]

            total_alerts = alert_stat["total_alerts"] or 0
            resolved = (alert_stat["confirmed_fraud"] or 0) + (alert_stat["false_positives"] or 0)
            fp_rate = ((alert_stat["false_positives"] or 0) / resolved) if resolved > 0 else 0.0

            return {
                "total_transactions": txn_stat["total_txns"] or 0,
                "total_volume_usd": float(txn_stat["total_vol"] or 0.0),
                "total_alerts": total_alerts,
                "open_alerts": alert_stat["open_alerts"] or 0,
                "confirmed_fraud": alert_stat["confirmed_fraud"] or 0,
                "false_positives": alert_stat["false_positives"] or 0,
                "blocked_count": alert_stat["blocked_count"] or 0,
                "review_count": alert_stat["review_count"] or 0,
                "false_positive_rate": round(fp_rate, 4),
                "prevented_fraud_usd": float(prevented)
            }

    def register_model_version(
        self,
        model_version: str,
        model_type: str,
        dataset: str,
        metrics_dict: Dict[str, Any],
        artefact_path: str
    ) -> None:
        """Register trained model version in database."""
        with self.get_conn() as conn:
            query = """
            INSERT INTO ml_models (model_version, model_type, dataset, metrics_json, artefact_path)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (model_version) DO UPDATE
            SET metrics_json = EXCLUDED.metrics_json, trained_at = now()
            """ if self.is_postgres else """
            INSERT OR REPLACE INTO ml_models (model_version, model_type, dataset, metrics_json, artefact_path, trained_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """
            conn.execute(query, (model_version, model_type, dataset, json.dumps(metrics_dict), artefact_path))

    def get_registered_models(self) -> List[Dict[str, Any]]:
        """List registered model versions and metrics."""
        with self.get_conn() as conn:
            cur = conn.execute("SELECT * FROM ml_models ORDER BY trained_at DESC")
            models = [dict(r) for r in cur.fetchall()]
            for m in models:
                if isinstance(m.get("metrics_json"), str):
                    try:
                        m["metrics_json"] = json.loads(m["metrics_json"])
                    except Exception:
                        pass
            return models


# Singleton instance
_db_instance: Optional[Database] = None


def get_db() -> Database:
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance
