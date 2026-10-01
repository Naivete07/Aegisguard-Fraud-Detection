"""Dataset Stream Replayer (PRD FR-1, Section 2.1).

Replays transactions from the dataset or simulation generator through Redis Streams or HTTP API
to test the end-to-end event-driven scoring pipeline.
"""
from __future__ import annotations

import argparse
import json
import time
import uuid

import httpx
import pandas as pd

from src.data.loaders import load_sparkov
from src.stream.publisher import StreamPublisher


def replay_via_http(tps: float = 10.0, max_count: int = 100, api_url: str = "http://localhost:8000"):
    print(f"[HTTP Replay] Loading Sparkov test samples...")
    df = load_sparkov().tail(max_count)
    delay = 1.0 / max(tps, 1.0)

    print(f"[HTTP Replay] Streaming {len(df)} transactions to {api_url}/score at {tps} TPS...")
    with httpx.Client(base_url=api_url, timeout=5.0) as client:
        for idx, row in df.iterrows():
            payload = {
                "txn_id": f"replay_{uuid.uuid4().hex[:10]}",
                "cc_num": str(row["cc_num"]),
                "amt": float(row["amt"]),
                "merchant": str(row["merchant"]),
                "category": str(row["category"]),
                "lat": float(row["lat"]),
                "long": float(row["long"]),
                "merch_lat": float(row["merch_lat"]),
                "merch_long": float(row["merch_long"]),
                "trans_date_trans_time": str(row["trans_date_trans_time"]),
                "channel": "POS",
                "city_pop": float(row["city_pop"])
            }
            try:
                res = client.post("/score", json=payload)
                data = res.json()
                print(f"  [Txn #{idx}] ${payload['amt']:.2f} @ {payload['merchant'][:20]} -> Decision: {data['decision'].upper()} (Risk: {data['risk_score']:.1%}, Latency: {data['latency_ms']}ms)")
            except Exception as e:
                print(f"  [Error] {e}")
            time.sleep(delay)
    print("[HTTP Replay] Completed.")


def replay_via_redis(tps: float = 20.0, max_count: int = 100, redis_url: str = "redis://localhost:6379/0"):
    print(f"[Redis Stream Replay] Connecting to Redis at {redis_url}...")
    try:
        pub = StreamPublisher(redis_url=redis_url)
        df = load_sparkov().tail(max_count)
        delay = 1.0 / max(tps, 1.0)
        print(f"[Redis Stream Replay] Publishing {len(df)} transactions at {tps} TPS...")

        for idx, row in df.iterrows():
            payload = {
                "txn_id": f"stream_{uuid.uuid4().hex[:10]}",
                "cc_num": str(row["cc_num"]),
                "amt": float(row["amt"]),
                "merchant": str(row["merchant"]),
                "category": str(row["category"]),
                "lat": float(row["lat"]),
                "long": float(row["long"]),
                "merch_lat": float(row["merch_lat"]),
                "merch_long": float(row["merch_long"]),
                "trans_date_trans_time": str(row["trans_date_trans_time"]),
                "channel": "POS",
                "city_pop": float(row["city_pop"])
            }
            msg_id = pub.publish_transaction(payload)
            print(f"  [Stream Msg: {msg_id}] Sent ${payload['amt']:.2f} for card {payload['cc_num'][-4:]}")
            time.sleep(delay)
        print("[Redis Stream Replay] Completed.")
    except Exception as e:
        print(f"[Redis Replay Error] {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["http", "redis"], default="http")
    parser.add_argument("--tps", type=float, default=10.0)
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--url", default="http://localhost:8000")
    args = parser.parse_args()

    if args.mode == "http":
        replay_via_http(tps=args.tps, max_count=args.count, api_url=args.url)
    else:
        replay_via_redis(tps=args.tps, max_count=args.count)
