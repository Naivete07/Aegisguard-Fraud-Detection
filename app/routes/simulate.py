"""Simulation and Demo Replay Endpoints for live testing and viva demonstrations."""
from __future__ import annotations

import random
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Body
from pydantic import BaseModel

from app.db import Database, get_db
from app.routes.score import compute_and_save_shap
from src.features.online_features import SPARKOV_CATEGORIES
from src.models.registry import ModelRegistry

router = APIRouter(prefix="/simulate", tags=["Demo & Simulation"])

MERCHANTS = [
    {"name": "fraud_Kirlin and Sons", "category": "grocery_pos", "lat": 40.7128, "lon": -74.0060},
    {"name": "fraud_Rippin, Kub and Mann", "category": "shopping_net", "lat": 34.0522, "lon": -118.2437},
    {"name": "fraud_Bahringer, Hilpert and Cole", "category": "misc_net", "lat": 41.8781, "lon": -87.6298},
    {"name": "fraud_Schultz-Rowe", "category": "shopping_pos", "lat": 29.7604, "lon": -95.3698},
    {"name": "Starbucks Coffee #421", "category": "food_dining", "lat": 35.2271, "lon": -80.8431},
    {"name": "Chevron Gas Station #88", "category": "gas_transport", "lat": 35.2280, "lon": -80.8440},
    {"name": "Target Store #1024", "category": "shopping_pos", "lat": 35.2300, "lon": -80.8400},
    {"name": "Netflix Monthly Subscription", "category": "entertainment", "lat": 37.7749, "lon": -122.4194},
    {"name": "Whole Foods Market", "category": "grocery_pos", "lat": 35.2250, "lon": -80.8420},
    {"name": "Apple Online Store", "category": "shopping_net", "lat": 37.3318, "lon": -122.0311},
]

DEMO_CARDS = [
    {"card_id": "4000123456789010", "lat": 35.2271, "lon": -80.8431, "city_pop": 850000, "age": 34, "gender": "F"},
    {"card_id": "5100987654321098", "lat": 40.7128, "lon": -74.0060, "city_pop": 8300000, "age": 45, "gender": "M"},
    {"card_id": "3700112233445566", "lat": 34.0522, "lon": -118.2437, "city_pop": 3900000, "age": 28, "gender": "M"},
    {"card_id": "6011009988776655", "lat": 41.8781, "lon": -87.6298, "city_pop": 2700000, "age": 52, "gender": "F"},
]


class SimulationScenarioRequest(BaseModel):
    scenario_type: str = "random"  # 'normal' | 'velocity_spike' | 'impossible_travel' | 'large_amount' | 'night_anomaly' | 'random'
    count: int = 1


@router.post("/batch")
def simulate_batch(
    req: Optional[SimulationScenarioRequest] = Body(default=None),
    db: Database = Depends(get_db)
):
    """Simulate single or multiple transactions under realistic fraud and legitimate patterns."""
    if req is None:
        req = SimulationScenarioRequest()
    registry = ModelRegistry.get_instance()
    results = []

    for _ in range(min(req.count, 50)):
        card = random.choice(DEMO_CARDS)
        now = datetime.utcnow()
        txn_id = f"sim_{uuid.uuid4().hex[:10]}"
        
        scenario = req.scenario_type
        if scenario == "random":
            scenario = random.choices(
                ["normal", "velocity_spike", "impossible_travel", "large_amount", "night_anomaly"],
                weights=[0.60, 0.10, 0.10, 0.10, 0.10]
            )[0]

        if scenario == "normal":
            merch = random.choice(MERCHANTS[4:])
            amt = round(random.uniform(8.50, 95.00), 2)
            merch_lat = card["lat"] + random.uniform(-0.05, 0.05)
            merch_lon = card["lon"] + random.uniform(-0.05, 0.05)
            dt_str = (now - timedelta(minutes=random.randint(1, 30))).isoformat()
        elif scenario == "velocity_spike":
            merch = random.choice(MERCHANTS[:4])
            amt = round(random.uniform(150.00, 750.00), 2)
            merch_lat = card["lat"] + random.uniform(-0.1, 0.1)
            merch_lon = card["lon"] + random.uniform(-0.1, 0.1)
            dt_str = now.isoformat()
            # Simulate prior fast transactions in state store
            for offset in [180, 120, 60]:
                registry.feature_engine.state_store.update_card_state(
                    card_id=card["card_id"],
                    txn_ts=now.timestamp() - offset,
                    amount=amt * 0.8,
                    merch_lat=merch_lat,
                    merch_long=merch_lon,
                    category=merch["category"],
                    merchant=merch["name"]
                )
        elif scenario == "impossible_travel":
            merch = random.choice(MERCHANTS[:4])
            amt = round(random.uniform(400.00, 1200.00), 2)
            # Far location (e.g. London / Paris / Tokyo coords)
            merch_lat = 51.5074 + random.uniform(-0.1, 0.1)
            merch_lon = -0.1278 + random.uniform(-0.1, 0.1)
            dt_str = now.isoformat()
            # Set prior location at home 2 minutes ago
            registry.feature_engine.state_store.update_card_state(
                card_id=card["card_id"],
                txn_ts=now.timestamp() - 120,
                amount=25.0,
                merch_lat=card["lat"],
                merch_long=card["lon"],
                category="gas_transport",
                merchant="Chevron Local"
            )
        elif scenario == "large_amount":
            merch = random.choice(MERCHANTS[:4])
            amt = round(random.uniform(980.00, 2850.00), 2)
            merch_lat = card["lat"] + random.uniform(-0.5, 0.5)
            merch_lon = card["lon"] + random.uniform(-0.5, 0.5)
            dt_str = now.isoformat()
        elif scenario == "night_anomaly":
            merch = random.choice(MERCHANTS[:4])
            amt = round(random.uniform(650.00, 1400.00), 2)
            merch_lat = card["lat"] + random.uniform(-1.0, 1.0)
            merch_lon = card["lon"] + random.uniform(-1.0, 1.0)
            # Set time to 02:30 AM
            night_dt = now.replace(hour=2, minute=30, second=0)
            dt_str = night_dt.isoformat()
        else:
            merch = random.choice(MERCHANTS)
            amt = round(random.uniform(15.0, 300.0), 2)
            merch_lat = card["lat"]
            merch_lon = card["lon"]
            dt_str = now.isoformat()

        payload = {
            "txn_id": txn_id,
            "cc_num": card["card_id"],
            "amt": amt,
            "trans_date_trans_time": dt_str,
            "merchant": merch["name"],
            "category": merch["category"],
            "lat": card["lat"],
            "long": card["lon"],
            "merch_lat": merch_lat,
            "merch_long": merch_lon,
            "city_pop": card["city_pop"],
            "age": card["age"],
            "gender": card["gender"],
            "channel": random.choice(["POS", "WEB", "APP"])
        }

        # Score transaction
        decision_res, feats_dict, feats_df, lat_ms = registry.score_transaction(payload, update_state_after=True)

        # Save transaction
        db.save_transaction(
            txn_id=txn_id,
            card_id=card["card_id"],
            merchant_id=merch["name"],
            amount=amt,
            txn_time=dt_str,
            channel=payload["channel"],
            lat=card["lat"],
            lon=card["lon"],
            features_dict=feats_dict,
            risk_score=decision_res.risk_score,
            anomaly_score=decision_res.anomaly_score,
            decision=decision_res.decision,
            model_version=registry.model_version
        )

        alert_id = None
        if decision_res.is_alert:
            alert_id = db.create_alert(
                txn_id=txn_id,
                risk_band=decision_res.risk_band,
                decision=decision_res.decision,
                model_version=registry.model_version
            )
            # Synchronously calculate SHAP for simulated alerts to be immediately inspectable in UI
            is_unsupervised_only = (
                decision_res.risk_score < 0.20
                and decision_res.anomaly_score >= 0.65
            )
            shap_payload = registry.explain_flagged(feats_df, is_unsupervised_only=is_unsupervised_only)
            if shap_payload:
                db.update_alert_shap(txn_id=txn_id, shap_dict=shap_payload)

        results.append({
            "txn_id": txn_id,
            "scenario": scenario,
            "card_id": card["card_id"],
            "merchant": merch["name"],
            "amount": amt,
            "decision": decision_res.decision,
            "risk_band": decision_res.risk_band,
            "risk_score": round(decision_res.risk_score, 4),
            "anomaly_score": round(decision_res.anomaly_score, 4),
            "alert_id": alert_id,
            "latency_ms": round(lat_ms, 2)
        })

    return {
        "status": "success",
        "generated_count": len(results),
        "transactions": results
    }
