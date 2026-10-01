"""Redis Stream Consumer Group Worker for Real-time Transaction Ingestion (PRD FR-1, FR-2, FR-14)."""
from __future__ import annotations

import json
import os
import signal
import sys
import time
from typing import Optional

import pandas as pd
import redis

from app.db import Database, get_db
from src.models.registry import ModelRegistry
from src.stream.publisher import STREAM_NAME

GROUP_NAME = "fraud_scoring_group"
CONSUMER_NAME = f"consumer_{os.getpid()}"


class StreamWorker:
    """Consumes transactions from Redis Stream, scores them, and writes idempotently to DB."""

    def __init__(self, redis_url: Optional[str] = None):
        url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self.redis_client = redis.from_url(url, decode_responses=True)
        self.db = get_db()
        self.registry = ModelRegistry.get_instance()
        self.running = True
        self._init_consumer_group()

    def _init_consumer_group(self) -> None:
        try:
            self.redis_client.xgroup_create(STREAM_NAME, GROUP_NAME, id="0", mkstream=True)
            print(f"[StreamWorker] Created consumer group '{GROUP_NAME}' on '{STREAM_NAME}'.")
        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP" in str(e):
                pass
            else:
                print(f"[StreamWorker] Group creation note: {e}")

    def run(self) -> None:
        print(f"[StreamWorker] Started {CONSUMER_NAME}, listening for events...")
        while self.running:
            try:
                # Read new messages with XREADGROUP
                entries = self.redis_client.xreadgroup(
                    groupname=GROUP_NAME,
                    consumername=CONSUMER_NAME,
                    streams={STREAM_NAME: ">"},
                    count=10,
                    block=1000
                )

                if not entries:
                    continue

                for stream_key, messages in entries:
                    for msg_id, data in messages:
                        self.process_message(msg_id, data)

            except Exception as e:
                print(f"[StreamWorker] Loop error: {e}")
                time.sleep(1)

    def process_message(self, msg_id: str, data: dict) -> None:
        try:
            raw_data = data.get("data")
            if not raw_data:
                self.redis_client.xack(STREAM_NAME, GROUP_NAME, msg_id)
                return

            txn = json.loads(raw_data)
            txn_id = txn.get("txn_id") or f"stream_{msg_id}"
            card_id = str(txn.get("cc_num") or txn.get("card_id") or "unknown_card")
            amount = float(txn.get("amt") or txn.get("amount") or 0.0)
            txn_time = str(txn.get("trans_date_trans_time") or txn.get("txn_time") or time.time())
            channel = str(txn.get("channel") or "STREAM")
            lat = float(txn.get("lat") or 35.0)
            lon = float(txn.get("long") or txn.get("lon") or -90.0)

            # Score transaction
            decision_res, feats_dict, feats_df, lat_ms = self.registry.score_transaction(txn, update_state_after=True)

            # Idempotent database write (PRD FR-2)
            self.db.save_transaction(
                txn_id=txn_id,
                card_id=card_id,
                merchant_id=str(txn.get("merchant", "unknown")),
                amount=amount,
                txn_time=txn_time,
                channel=channel,
                lat=lat,
                lon=lon,
                features_dict=feats_dict,
                risk_score=decision_res.risk_score,
                anomaly_score=decision_res.anomaly_score,
                decision=decision_res.decision,
                model_version=self.registry.model_version
            )

            # If alert, store and calculate SHAP asynchronously
            if decision_res.is_alert:
                alert_id = self.db.create_alert(
                    txn_id=txn_id,
                    risk_band=decision_res.risk_band,
                    decision=decision_res.decision,
                    model_version=self.registry.model_version
                )
                is_unsupervised_only = (
                    decision_res.risk_score < 0.20
                    and decision_res.anomaly_score >= 0.65
                )
                shap_payload = self.registry.explain_flagged(feats_df, is_unsupervised_only=is_unsupervised_only)
                if shap_payload:
                    self.db.update_alert_shap(txn_id=txn_id, shap_dict=shap_payload)

            # Acknowledge processed message
            self.redis_client.xack(STREAM_NAME, GROUP_NAME, msg_id)

        except Exception as e:
            print(f"[StreamWorker] Failed processing msg {msg_id}: {e}")
            # Still acknowledge to prevent endless poison pill loop
            self.redis_client.xack(STREAM_NAME, GROUP_NAME, msg_id)

    def stop(self) -> None:
        self.running = False


def main():
    worker = StreamWorker()

    def handle_sig(sig, frame):
        print("\n[StreamWorker] Shutting down...")
        worker.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)
    worker.run()


if __name__ == "__main__":
    main()
