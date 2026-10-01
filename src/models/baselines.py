"""Sprint 1 baselines: Logistic Regression + plain XGBoost, chronological split.

Threshold is chosen on the validation slice (max F1) and applied to the test slice,
so test numbers are not tuned on test data. Output: reports/baselines.csv
"""
import argparse
import time

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_curve
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from src.config import REPORTS, SCHEMA, SEED
from src.data.loaders import chrono_split, load

IEEE_COLS = (
    ["TransactionAmt", "ProductCD", "addr1", "addr2", "dist1", "dist2", "P_emaildomain", "R_emaildomain", "DeviceType"]
    + [f"card{i}" for i in range(1, 7)]
    + [f"C{i}" for i in range(1, 15)]
    + [f"D{i}" for i in range(1, 16)]
    + [f"M{i}" for i in range(1, 10)]
)


def _codes(s: pd.Series) -> pd.Series:
    return s.astype("category").cat.codes.astype("float32")  # NaN -> -1


def make_xy(name: str, df: pd.DataFrame):
    target, _ = SCHEMA[name]
    y = df[target].astype(int)
    if name == "ulb":
        X = df[[f"V{i}" for i in range(1, 29)] + ["Amount"]].copy()
    elif name == "sparkov":
        t = df["trans_date_trans_time"]
        X = pd.DataFrame({
            "amt": df["amt"], "city_pop": df["city_pop"],
            "lat": df["lat"], "long": df["long"],
            "merch_lat": df["merch_lat"], "merch_long": df["merch_long"],
            "hour": t.dt.hour, "dow": t.dt.dayofweek,
            "age": (t - df["dob"]).dt.days / 365.25,
            "category": _codes(df["category"]), "gender": _codes(df["gender"]),
        })
    elif name == "ieee":
        cols = [c for c in IEEE_COLS if c in df.columns]
        X = df[cols].copy()
        for c in [c for c in X.columns if not pd.api.types.is_numeric_dtype(X[c])]:
            X[c] = _codes(X[c])
    else:
        raise ValueError(name)
    return X.astype("float32"), y


def evaluate(model, Xtr, ytr, Xva, yva, Xte, yte):
    t0 = time.time()
    model.fit(Xtr, ytr)
    fit_s = time.time() - t0
    pva, pte = model.predict_proba(Xva)[:, 1], model.predict_proba(Xte)[:, 1]
    prec, rec, thr = precision_recall_curve(yva, pva)
    f1 = 2 * prec[:-1] * rec[:-1] / (prec[:-1] + rec[:-1] + 1e-12)
    t = thr[int(np.argmax(f1))]
    pred = pte >= t
    tp = int(((pred == 1) & (yte == 1)).sum())
    p = tp / max(int(pred.sum()), 1)
    r = tp / max(int((yte == 1).sum()), 1)
    return {
        "pr_auc": round(average_precision_score(yte, pte), 4),
        "precision": round(p, 4), "recall": round(r, 4),
        "f1": round(2 * p * r / (p + r + 1e-12), 4),
        "threshold": round(float(t), 4), "fit_seconds": round(fit_s, 1),
    }


def run(name: str):
    df = load(name)
    tr, va, te = chrono_split(df)
    (Xtr, ytr), (Xva, yva), (Xte, yte) = make_xy(name, tr), make_xy(name, va), make_xy(name, te)
    print(f"[{name}] train={len(tr):,} val={len(va):,} test={len(te):,} | test fraud={int(yte.sum())}")

    spw = float((ytr == 0).sum() / max((ytr == 1).sum(), 1))
    models = {
        "LogisticRegression": make_pipeline(
            SimpleImputer(strategy="median"), StandardScaler(),
            LogisticRegression(class_weight="balanced", max_iter=1000, random_state=SEED)),
        "XGBoost": XGBClassifier(
            n_estimators=300, max_depth=6, learning_rate=0.1, subsample=0.8, colsample_bytree=0.8,
            scale_pos_weight=spw, tree_method="hist", eval_metric="aucpr", n_jobs=-1, random_state=SEED),
    }
    rows = []
    for mname, model in models.items():
        res = evaluate(model, Xtr, ytr, Xva, yva, Xte, yte)
        print(f"  {mname}: {res}")
        rows.append({"dataset": name, "model": mname, **res})
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", nargs="+", default=["ulb", "sparkov", "ieee"], choices=list(SCHEMA))
    args = ap.parse_args()
    out = [r for d in args.datasets for r in run(d)]
    REPORTS.mkdir(exist_ok=True)
    pd.DataFrame(out).to_csv(REPORTS / "baselines.csv", index=False)
    print("\n", pd.DataFrame(out).to_string(index=False))
    print("\nSaved reports/baselines.csv")
