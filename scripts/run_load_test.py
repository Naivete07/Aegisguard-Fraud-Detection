"""Automated Latency & Throughput Load Test Runner (PRD NFR-1 & NFR-2).

Benchmarks synchronous /score endpoint with concurrent worker threads.
Measures p50, p90, p95, p99 latencies and sustained Transactions-Per-Second (TPS).
"""
import argparse
import random
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

import httpx
import numpy as np

CARDS = [f"400012345678{i:04d}" for i in range(50)]
CATEGORIES = ["grocery_pos", "shopping_net", "misc_net", "food_dining", "gas_transport"]
MERCHANTS = ["fraud_Kirlin and Sons", "Target Store #102", "Starbucks Coffee", "Amazon Online"]


def send_score_request(client: httpx.Client, base_url: str) -> float:
    card = random.choice(CARDS)
    amt = round(random.uniform(10.0, 300.0), 2)
    lat = 35.2271
    lon = -80.8431

    payload = {
        "txn_id": f"bench_{uuid.uuid4().hex[:12]}",
        "cc_num": card,
        "amt": amt,
        "merchant": random.choice(MERCHANTS),
        "category": random.choice(CATEGORIES),
        "channel": "POS",
        "lat": lat,
        "long": lon,
        "merch_lat": lat,
        "merch_long": lon,
        "city_pop": 50000,
        "age": 35
    }

    t0 = time.perf_counter()
    resp = client.post(f"{base_url}/score", json=payload, timeout=5.0)
    dur_ms = (time.perf_counter() - t0) * 1000.0
    
    if resp.status_code != 200:
        raise RuntimeError(f"Request failed: {resp.status_code} - {resp.text}")
    return dur_ms


def run_benchmark(base_url: str = "http://localhost:8000", total_requests: int = 500, concurrency: int = 10):
    print(f"\n=======================================================")
    print(f" AegisGuard Scoring Engine Benchmark (PRD NFR-1 / NFR-2)")
    print(f" Target: {base_url} | Requests: {total_requests} | Concurrency: {concurrency}")
    print(f"=======================================================\n")

    latencies: List[float] = []
    t_start = time.perf_counter()

    with httpx.Client() as client:
        # Check health first
        try:
            h = client.get(f"{base_url}/health", timeout=3.0)
            print(f"[Health Check] Status: {h.json().get('status')} | Active Model: {h.json().get('active_model_version')}\n")
        except Exception as e:
            print(f"[Error] Could not connect to API at {base_url}: {e}")
            print("Make sure the FastAPI server is running (`uvicorn app.main:app --port 8000`)")
            return

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(send_score_request, client, base_url) for _ in range(total_requests)]
            for fut in as_completed(futures):
                try:
                    lat_ms = fut.result()
                    latencies.append(lat_ms)
                except Exception as e:
                    print(f"Request error: {e}")

    total_time = time.perf_counter() - t_start
    tps = len(latencies) / total_time

    arr = np.array(latencies)
    p50 = float(np.percentile(arr, 50))
    p90 = float(np.percentile(arr, 90))
    p95 = float(np.percentile(arr, 95))
    p99 = float(np.percentile(arr, 99))
    avg = float(np.mean(arr))

    print(f"--- Benchmark Results ---")
    print(f"Total Completed Requests: {len(latencies):,} in {total_time:.2f}s")
    print(f"Throughput (TPS):         {tps:.1f} req/s (Target: >= 100 TPS)")
    print(f"Average Latency:          {avg:.2f} ms")
    print(f"p50 Latency:              {p50:.2f} ms")
    print(f"p90 Latency:              {p90:.2f} ms")
    print(f"p95 Latency:              {p95:.2f} ms (NFR-1 Target: < 200 ms)")
    print(f"p99 Latency:              {p99:.2f} ms")
    print(f"-------------------------")

    if p95 < 200.0:
        print("[PASS] NFR-1 LATENCY TARGET MET (p95 < 200ms)")
    else:
        print("[WARN] Latency exceeded target")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--requests", type=int, default=500)
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()
    run_benchmark(args.url, args.requests, args.concurrency)
