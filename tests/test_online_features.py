import pytest
from datetime import datetime, timedelta
from src.features.online_features import CardStateStore, OnlineFeatureEngine, ALL_FEATURE_COLUMNS


def test_card_state_store_in_memory():
    store = CardStateStore()
    card_id = "test_card_123"
    
    initial_state = store.get_card_state(card_id)
    assert initial_state["n_txns"] == 0
    assert initial_state["amt_sum"] == 0.0

    t0 = datetime(2026, 1, 1, 12, 0, 0).timestamp()
    store.update_card_state(
        card_id=card_id,
        txn_ts=t0,
        amount=100.0,
        merch_lat=35.0,
        merch_long=-80.0,
        category="grocery_pos",
        merchant="Walmart"
    )

    updated = store.get_card_state(card_id)
    assert updated["n_txns"] == 1
    assert updated["amt_sum"] == 100.0
    assert updated["categories"] == ["grocery_pos"]
    assert updated["merchants"] == ["Walmart"]


def test_online_feature_engine_velocity_and_speed():
    engine = OnlineFeatureEngine()
    card_id = "card_vel_test"

    t0 = datetime(2026, 1, 1, 10, 0, 0)
    
    # 1st transaction (home base)
    tx1 = {
        "cc_num": card_id,
        "amt": 50.0,
        "trans_date_trans_time": t0.isoformat(),
        "lat": 35.2271,
        "long": -80.8431,
        "merch_lat": 35.2271,
        "merch_long": -80.8431,
        "category": "grocery_pos",
        "merchant": "Local Grocery",
        "city_pop": 50000
    }
    df1, f1 = engine.compute_features(tx1, update_state_after=True)
    
    assert list(df1.columns) == ALL_FEATURE_COLUMNS
    assert f1["txn_count_1h"] == 0.0
    assert f1["dist_home_km"] == pytest.approx(0.0, abs=0.1)
    assert f1["speed_kmh"] == 0.0
    assert f1["is_new_category"] == 1.0

    # 2nd transaction 10 minutes later, 500 km away (implied travel speed ~3000 km/h)
    t1 = t0 + timedelta(minutes=10)
    tx2 = {
        "cc_num": card_id,
        "amt": 850.0,
        "trans_date_trans_time": t1.isoformat(),
        "lat": 35.2271,
        "long": -80.8431,
        "merch_lat": 39.9526,
        "merch_long": -75.1652,
        "category": "grocery_pos",
        "merchant": "Remote Store",
        "city_pop": 50000
    }
    df2, f2 = engine.compute_features(tx2, update_state_after=True)
    
    assert f2["txn_count_1h"] == 1.0
    assert f2["amt_sum_1h"] == 50.0
    assert f2["dist_prev_km"] > 400.0
    assert f2["speed_kmh"] > 1000.0
    assert f2["is_new_category"] == 0.0  # Already visited grocery_pos
    assert f2["is_new_merchant"] == 1.0
