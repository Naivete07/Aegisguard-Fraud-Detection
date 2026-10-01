import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from src.features.behavioural import haversine_km, sparkov_features


def _frame(times, amts, card=1):
    return pd.DataFrame({
        "cc_num": card, "trans_date_trans_time": pd.to_datetime(times), "amt": amts,
        "lat": 28.6, "long": 77.2, "merch_lat": 28.7, "merch_long": 77.3,
        "category": "a", "merchant": "m"})


def test_haversine_delhi_mumbai():
    assert 1100 < haversine_km(28.6139, 77.2090, 19.0760, 72.8777) < 1200


def test_velocity_windows_exclude_current_and_respect_window():
    t0 = pd.Timestamp("2020-01-01 00:00:00")
    df = _frame([t0, t0 + pd.Timedelta(minutes=30), t0 + pd.Timedelta(hours=2)], [10.0, 20.0, 30.0])
    f = sparkov_features(df)
    assert list(f["txn_count_1h"]) == [0, 1, 0]      # row 2: the 30-min-old txn is outside 1h
    assert list(f["txn_count_24h"]) == [0, 1, 2]
    assert list(f["amt_sum_24h"]) == [0, 10, 30]
    assert f["is_new_category"].tolist() == [1, 0, 0]


def test_point_in_time_no_future_leakage():
    rng = np.random.default_rng(1)
    n = 400
    df = pd.DataFrame({
        "cc_num": rng.integers(1, 6, n),
        "trans_date_trans_time": pd.Timestamp("2020-01-01") + pd.to_timedelta(np.sort(rng.integers(0, 86400 * 20, n)), unit="s"),
        "amt": rng.exponential(50, n), "lat": rng.normal(40, 2, n), "long": rng.normal(-90, 2, n),
        "merch_lat": rng.normal(40, 2, n), "merch_long": rng.normal(-90, 2, n),
        "category": rng.choice(list("abc"), n), "merchant": rng.choice(list("wxyz"), n)})
    full = sparkov_features(df)
    k = 250
    part = sparkov_features(df.iloc[:k])
    assert_frame_equal(full.iloc[:k], part, check_exact=False, rtol=1e-4, atol=1e-4)
