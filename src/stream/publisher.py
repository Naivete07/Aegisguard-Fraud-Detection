"""Redis Streams transaction publisher (PRD FR-1, NFR-2)."""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import redis

STREAM_NAME = "stream:transactions"


class StreamPublisher:
    """Publishes transaction events to Redis Streams."""

    def __init__(self, redis_url: Optional[str] = None):
        url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self.client = redis.from_url(url, decode_responses=True)

    def publish_transaction(self, txn_dict: Dict[str, Any]) -> str:
        """Publish a single transaction event."""
        if "txn_id" not in txn_dict:
            txn_dict["txn_id"] = f"stream_{uuid.uuid4().hex[:12]}"
        if "trans_date_trans_time" not in txn_dict and "txn_time" not in txn_dict:
            txn_dict["trans_date_trans_time"] = datetime.utcnow().isoformat()
            
        payload = {"data": json.dumps(txn_dict)}
        msg_id = self.client.xadd(STREAM_NAME, payload)
        return msg_id

    def replay_batch(
        self,
        transactions: List[Dict[str, Any]],
        tps: float = 20.0
    ) -> int:
        """Replay a list of transactions at the given transactions-per-second rate."""
        delay = 1.0 / max(tps, 1.0)
        count = 0
        for tx in transactions:
            self.publish_transaction(tx)
            count += 1
            time.sleep(delay)
        return count
