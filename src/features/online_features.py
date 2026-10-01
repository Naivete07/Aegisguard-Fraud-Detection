"""Online point-in-time feature extraction for real-time transaction scoring.

Ensures zero train/serve skew by computing the exact same behavioural features
defined in src/features/behavioural.py, backed by Redis or an in-memory state store.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.features.behavioural import FEATURE_COLUMNS, WINDOWS, MIN_HISTORY, haversine_km

# Category mapping matching pandas categorical codes on standard Sparkov
SPARKOV_CATEGORIES = [
    "entertainment", "food_dining", "gas_transport", "grocery_net",
    "grocery_pos", "health_fitness", "home", "kids_pets", "misc_net",
    "misc_pos", "personal_care", "shopping_net", "shopping_pos", "travel"
]
CATEGORY_TO_CODE = {cat: idx for idx, cat in enumerate(sorted(SPARKOV_CATEGORIES))}
GENDER_TO_CODE = {"F": 0, "M": 1, "f": 0, "m": 1}

BASE_COLUMNS = [
    "amt", "city_pop", "lat", "long", "merch_lat", "merch_long",
    "hour", "dow", "age", "category", "gender"
]
ALL_FEATURE_COLUMNS = BASE_COLUMNS + list(FEATURE_COLUMNS)


class CardStateStore:
    """Maintains card history for online feature engineering.
    
    Uses Redis when available, with automatic fallback to an in-memory LRU store.
    """

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_client = None
        url = redis_url or os.environ.get("REDIS_URL")
        if url:
            try:
                import redis
                client = redis.from_url(url, decode_responses=True, socket_timeout=1.5)
                client.ping()
                self.redis_client = client
            except Exception:
                self.redis_client = None
        self._memory_store: Dict[str, Dict[str, Any]] = {}

    def get_card_state(self, card_id: str) -> Dict[str, Any]:
        """Fetch historical state for a card."""
        key = f"card_state:{card_id}"
        if self.redis_client:
            try:
                data = self.redis_client.get(key)
                if data:
                    return json.loads(data)
            except Exception:
                pass
        return self._memory_store.get(card_id, {
            "n_txns": 0,
            "amt_sum": 0.0,
            "amt_sq_sum": 0.0,
            "categories": [],
            "merchants": [],
            "last_txn_ts": None,
            "last_merch_lat": None,
            "last_merch_long": None,
            "recent_txns": []  # List of [timestamp_sec, amount] within 7 days
        })

    def update_card_state(
        self,
        card_id: str,
        txn_ts: float,
        amount: float,
        merch_lat: float,
        merch_long: float,
        category: str,
        merchant: str
    ) -> None:
        """Update card state with newly scored transaction."""
        state = self.get_card_state(card_id)
        state["n_txns"] += 1
        state["amt_sum"] += float(amount)
        state["amt_sq_sum"] += float(amount * amount)
        
        # Keep unique categories & merchants (capped to last 100 for memory)
        if category not in state["categories"]:
            state["categories"].append(category)
            if len(state["categories"]) > 100:
                state["categories"].pop(0)
        if merchant not in state["merchants"]:
            state["merchants"].append(merchant)
            if len(state["merchants"]) > 100:
                state["merchants"].pop(0)

        # Update last location & timestamp
        state["last_txn_ts"] = txn_ts
        state["last_merch_lat"] = float(merch_lat)
        state["last_merch_long"] = float(merch_long)

        # Prune transactions older than 7 days (604800s)
        cutoff = txn_ts - 604800
        recent = [tx for tx in state["recent_txns"] if tx[0] >= cutoff]
        recent.append([txn_ts, float(amount)])
        state["recent_txns"] = recent

        key = f"card_state:{card_id}"
        if self.redis_client:
            try:
                # Expire after 30 days of inactivity
                self.redis_client.setex(key, 86400 * 30, json.dumps(state))
                return
            except Exception:
                pass
        self._memory_store[card_id] = state


class OnlineFeatureEngine:
    """Extracts features in point-in-time fashion for single transactions."""

    def __init__(self, state_store: Optional[CardStateStore] = None):
        self.state_store = state_store or CardStateStore()

    def compute_features(
        self,
        txn: Dict[str, Any],
        update_state_after: bool = False
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """Compute point-in-time features for a transaction payload.
        
        Returns:
            df_features: 1-row DataFrame ready for model inference (columns match ALL_FEATURE_COLUMNS).
            feature_dict: Dictionary of all computed feature values.
        """
        # Parse timestamp
        raw_ts = txn.get("trans_date_trans_time") or txn.get("txn_time") or txn.get("timestamp")
        if isinstance(raw_ts, str):
            try:
                dt = pd.to_datetime(raw_ts)
            except Exception:
                dt = datetime.utcnow()
        elif isinstance(raw_ts, (int, float)):
            dt = datetime.utcfromtimestamp(raw_ts)
        elif isinstance(raw_ts, (pd.Timestamp, datetime)):
            dt = pd.to_datetime(raw_ts)
        else:
            dt = datetime.utcnow()

        try:
            if hasattr(dt, 'tz') and dt.tz is not None:
                dt = dt.tz_convert(None)
            elif hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
        except Exception:
            try:
                dt = pd.to_datetime(dt).tz_localize(None)
            except Exception:
                pass

        txn_sec = (dt - pd.Timestamp("1970-01-01")).total_seconds()
        card_id = str(txn.get("cc_num") or txn.get("card_id") or "default_card")
        amount = float(txn.get("amt") or txn.get("amount") or 0.0)
        
        lat = float(txn.get("lat") or 0.0)
        lon = float(txn.get("long") or txn.get("lon") or 0.0)
        merch_lat = float(txn.get("merch_lat") or lat)
        merch_long = float(txn.get("merch_long") or lon)
        
        category = str(txn.get("category") or "misc_pos")
        merchant = str(txn.get("merchant") or "unknown_merchant")
        gender = str(txn.get("gender") or "M")
        city_pop = float(txn.get("city_pop") or 10000.0)

        # Parse DOB / Age
        dob_raw = txn.get("dob")
        if dob_raw:
            try:
                dob_dt = pd.to_datetime(dob_raw)
                if hasattr(dob_dt, 'tz') and dob_dt.tz is not None:
                    dob_dt = dob_dt.tz_convert(None)
                elif hasattr(dob_dt, 'tzinfo') and dob_dt.tzinfo is not None:
                    dob_dt = dob_dt.replace(tzinfo=None)
                age = float((dt - dob_dt).days / 365.25)
            except Exception:
                age = float(txn.get("age", 40.0))
        else:
            age = float(txn.get("age", 40.0))

        # Retrieve card prior state (point-in-time before this transaction)
        state = self.state_store.get_card_state(card_id)
        n_prev = state["n_txns"]
        prev_sum = state["amt_sum"]
        prev_sq_sum = state["amt_sq_sum"]
        last_ts = state["last_txn_ts"]
        last_mlat = state["last_merch_lat"]
        last_mlon = state["last_merch_long"]
        recent_txns = state["recent_txns"]

        # Velocity window features
        v_feats: Dict[str, float] = {}
        for w_name, w_sec in WINDOWS.items():
            window_start = txn_sec - w_sec
            txs_in_w = [t for t in recent_txns if t[0] >= window_start and t[0] < txn_sec]
            v_feats[f"txn_count_{w_name}"] = float(len(txs_in_w))
            v_feats[f"amt_sum_{w_name}"] = float(sum(t[1] for t in txs_in_w))

        # Mean & z-score
        if n_prev > 0:
            mean_amt = prev_sum / n_prev
            var_amt = max(0.0, (prev_sq_sum / n_prev) - (mean_amt ** 2))
            std_amt = np.sqrt(var_amt)
            amt_z = float((amount - mean_amt) / std_amt) if (n_prev >= MIN_HISTORY and std_amt > 1e-6) else 0.0
            amt_over_mean = float(amount / mean_amt) if mean_amt > 1e-6 else 1.0
        else:
            amt_z = 0.0
            amt_over_mean = 1.0

        # Geo & travel speed
        dist_home = float(haversine_km(lat, lon, merch_lat, merch_long))
        if last_ts is not None and last_mlat is not None and last_mlon is not None:
            secs_since_last = max(0.0, txn_sec - last_ts)
            dist_prev = float(haversine_km(last_mlat, last_mlon, merch_lat, merch_long))
            speed_kmh = float(dist_prev / (max(secs_since_last, 60.0) / 3600.0))
        else:
            secs_since_last = 0.0
            dist_prev = 0.0
            speed_kmh = 0.0

        hour = dt.hour
        dow = dt.dayofweek if hasattr(dt, "dayofweek") else dt.weekday()
        is_night = 1.0 if (hour >= 22 or hour <= 3) else 0.0
        log_amt = float(np.log1p(amount))
        is_new_category = 0.0 if category in state["categories"] else 1.0
        is_new_merchant = 0.0 if merchant in state["merchants"] else 1.0

        # Categorical codes
        cat_code = float(CATEGORY_TO_CODE.get(category, -1.0))
        gender_code = float(GENDER_TO_CODE.get(gender, 0.0))

        feat_dict = {
            "amt": float(amount),
            "city_pop": float(city_pop),
            "lat": float(lat),
            "long": float(lon),
            "merch_lat": float(merch_lat),
            "merch_long": float(merch_long),
            "hour": float(hour),
            "dow": float(dow),
            "age": float(age),
            "category": float(cat_code),
            "gender": float(gender_code),
            # Behavioural
            "is_night": is_night,
            "log_amt": log_amt,
            "dist_home_km": dist_home,
            "n_prev_txn": float(n_prev),
            "secs_since_last": secs_since_last,
            "dist_prev_km": dist_prev,
            "speed_kmh": speed_kmh,
            "amt_z": amt_z,
            "amt_over_card_mean": amt_over_mean,
            "is_new_category": is_new_category,
            "is_new_merchant": is_new_merchant,
            **v_feats
        }

        # Build single row dataframe
        df_row = pd.DataFrame([feat_dict])[ALL_FEATURE_COLUMNS].astype("float32")

        if update_state_after:
            self.state_store.update_card_state(
                card_id=card_id,
                txn_ts=txn_sec,
                amount=amount,
                merch_lat=merch_lat,
                merch_long=merch_long,
                category=category,
                merchant=merchant
            )

        return df_row, feat_dict
