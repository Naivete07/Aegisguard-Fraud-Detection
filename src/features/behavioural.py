"""Point-in-time behavioural features for card-transaction data (Sparkov schema).

Every feature for a transaction uses ONLY that card's earlier transactions (never the current
row's future), so there is no label/time leakage. tests/test_features.py enforces this.

Required columns: cc_num, trans_date_trans_time, amt, lat, long, merch_lat, merch_long,
                  category, merchant
"""
import numpy as np
import pandas as pd

WINDOWS = {"1h": 3600, "24h": 86400, "7d": 604800}
MIN_HISTORY = 5  # transactions needed before the amount z-score is trusted

FEATURE_COLUMNS = (
    ["is_night", "log_amt", "dist_home_km", "n_prev_txn", "secs_since_last", "dist_prev_km", "speed_kmh",
     "amt_z", "amt_over_card_mean", "is_new_category", "is_new_merchant"]
    + [f"txn_count_{w}" for w in WINDOWS]
    + [f"amt_sum_{w}" for w in WINDOWS]
)


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = (np.radians(np.asarray(x, dtype="float64")) for x in (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * np.arcsin(np.sqrt(a))


def sparkov_features(df: pd.DataFrame) -> pd.DataFrame:
    """Return FEATURE_COLUMNS for every row of df, aligned to df.index (index must be unique)."""
    d = df.sort_values(["cc_num", "trans_date_trans_time"], kind="stable")
    n = len(d)
    card = d["cc_num"].to_numpy()
    ts = (d["trans_date_trans_time"] - pd.Timestamp("1970-01-01")).dt.total_seconds().to_numpy()
    amt = d["amt"].to_numpy(dtype="float64")

    out = {c: np.zeros(n) for c in FEATURE_COLUMNS}
    out["amt_z"][:] = 0.0

    starts = np.r_[0, np.flatnonzero(card[1:] != card[:-1]) + 1]
    ends = np.r_[starts[1:], n]
    for s, e in zip(starts, ends):
        t, a = ts[s:e], amt[s:e]
        i = np.arange(e - s)
        cs = np.r_[0.0, np.cumsum(a)]        # cs[i] = sum of amounts strictly before row i
        cs2 = np.r_[0.0, np.cumsum(a * a)]
        for w, sec in WINDOWS.items():
            lo = np.searchsorted(t, t - sec, side="left")
            out[f"txn_count_{w}"][s:e] = i - lo
            out[f"amt_sum_{w}"][s:e] = cs[i] - cs[lo]
        out["n_prev_txn"][s:e] = i
        with np.errstate(divide="ignore", invalid="ignore"):
            mean = np.where(i > 0, cs[i] / np.maximum(i, 1), np.nan)
            var = np.where(i > 0, cs2[i] / np.maximum(i, 1) - mean ** 2, np.nan)
            std = np.sqrt(np.maximum(var, 0.0))
            z = np.where((i >= MIN_HISTORY) & (std > 0), (a - mean) / std, 0.0)
            ratio = np.where(mean > 0, a / mean, np.nan)
        out["amt_z"][s:e] = z
        out["amt_over_card_mean"][s:e] = ratio

    # previous-transaction features (shift within card)
    same = np.r_[False, card[1:] == card[:-1]]
    prev_ts = np.r_[np.nan, ts[:-1]]
    dt = np.where(same, ts - prev_ts, np.nan)
    mlat, mlon = d["merch_lat"].to_numpy(), d["merch_long"].to_numpy()
    dist_prev = np.where(same, haversine_km(np.r_[np.nan, mlat[:-1]], np.r_[np.nan, mlon[:-1]], mlat, mlon), np.nan)
    out["secs_since_last"] = dt
    out["dist_prev_km"] = dist_prev
    out["speed_kmh"] = dist_prev / (np.maximum(dt, 60.0) / 3600.0)  # dt floored at 60s to avoid inf

    hour = d["trans_date_trans_time"].dt.hour.to_numpy()
    out["is_night"] = ((hour >= 22) | (hour <= 3)).astype(float)
    out["log_amt"] = np.log1p(amt)
    out["dist_home_km"] = haversine_km(d["lat"], d["long"], d["merch_lat"], d["merch_long"])
    out["is_new_category"] = (d.groupby(["cc_num", "category"], sort=False).cumcount() == 0).to_numpy().astype(float)
    out["is_new_merchant"] = (d.groupby(["cc_num", "merchant"], sort=False).cumcount() == 0).to_numpy().astype(float)

    res = pd.DataFrame(out, index=d.index)[FEATURE_COLUMNS].astype("float32")
    return res.loc[df.index]
