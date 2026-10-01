"""Locust Load Testing File for AegisGuard Scoring Engine (PRD NFR-1 & NFR-2).

Run with:
  locust -f tests/locustfile.py --headless -u 20 -r 5 --run-time 30s --host http://localhost:8000
"""
import random
import uuid
from locust import HttpUser, between, task

CARDS = [f"400012345678{i:04d}" for i in range(100)]
CATEGORIES = ["grocery_pos", "shopping_net", "misc_net", "food_dining", "gas_transport", "travel"]
MERCHANTS = ["fraud_Kirlin and Sons", "Target Store #102", "Starbucks Coffee", "Amazon Online", "Chevron #44"]


class ScoringUser(HttpUser):
    wait_time = between(0.01, 0.05)  # High throughput simulation

    @task(10)
    def score_transaction(self):
        card = random.choice(CARDS)
        cat = random.choice(CATEGORIES)
        merch = random.choice(MERCHANTS)
        amt = round(random.uniform(5.0, 450.0), 2)
        lat = random.uniform(30.0, 45.0)
        lon = random.uniform(-100.0, -75.0)

        payload = {
            "txn_id": f"locust_{uuid.uuid4().hex[:12]}",
            "cc_num": card,
            "amt": amt,
            "merchant": merch,
            "category": cat,
            "channel": "POS",
            "lat": lat,
            "long": lon,
            "merch_lat": lat + random.uniform(-0.02, 0.02),
            "merch_long": lon + random.uniform(-0.02, 0.02),
            "city_pop": 250000,
            "age": 38
        }
        self.client.post("/score", json=payload)

    @task(2)
    def fetch_alerts(self):
        self.client.get("/alerts?limit=20")

    @task(1)
    def health_check(self):
        self.client.get("/health")
