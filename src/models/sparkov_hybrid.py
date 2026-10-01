"""Sprint 2: hybrid ablation on Sparkov.  XGBoost only | Isolation Forest only | OR-fusion | Stacked.

  python -m src.models.sparkov_hybrid                                  # main ablation table
  python -m src.models.sparkov_hybrid --list-categories                # fraud count per merchant category
  python -m src.models.sparkov_hybrid --holdout-category shopping_net  # held-out fraud-type experiment

Held-out mode: fraud rows of that category are removed from train AND validation (so neither the models
nor the thresholds ever see that fraud type). Test is untouched; we report recall on the held-out type.
All thresholds are chosen on validation, never on test.
"""
import argparse

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, precision_recall_curve
from xgboost import XGBClassifier

from src.config import REPORTS, SEED
from src.features.behavioural import FEATURE_COLUMNS
from src.models.sparkov_data import get_sparkov_matrix

ANOMALY_COLS = FEATURE_COLUMNS + ["amt", "hour"]  # behavioural columns only, no IDs / category codes


def best_threshold(y, p):
    prec, rec, thr = precision_recall_curve(y, p)
    f1 = 2 * prec[:-1] * rec[:-1] / (prec[:-1] + rec[:-1] + 1e-12)
    return float(thr[int(np.argmax(f1))])


def summarize(y, pred, score=None, held=None):
    y, pred = np.asarray(y), np.asarray(pred).astype(bool)
    tp = int((pred & (y == 1)).sum())
    p, r = tp / max(int(pred.sum()), 1), tp / max(int((y == 1).sum()), 1)
    d = {"pr_auc": round(average_precision_score(y, score), 4) if score is not None else np.nan,
         "precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r + 1e-12), 4),
         "alerts": int(pred.sum())}
    if held is not None:
        m, o = held & (y == 1), (~held) & (y == 1)
        d["recall_heldout"] = round(float(pred[m].mean()), 4) if m.sum() else np.nan
        d["recall_other"] = round(float(pred[o].mean()), 4) if o.sum() else np.nan
        d["n_heldout_test_fraud"] = int(m.sum())
    return d


def xgb(spw):
    return XGBClassifier(n_estimators=300, max_depth=6, learning_rate=0.1, subsample=0.8, colsample_bytree=0.8,
                         scale_pos_weight=spw, tree_method="hist", eval_metric="aucpr", n_jobs=-1, random_state=SEED)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdout-category", default=None)
    ap.add_argument("--list-categories", action="store_true")
    ap.add_argument("--if-alert-rate", type=float, default=0.005, help="share of val transactions the IF branch may flag in OR-fusion")
    args = ap.parse_args()

    X, y, df = get_sparkov_matrix()
    cats = df["category"].to_numpy()
    n = len(y)
    i, j = int(n * 0.70), int(n * 0.85)
    yv = y.to_numpy()

    if args.list_categories:
        t = pd.DataFrame({"category": cats, "fraud": yv, "part": np.where(np.arange(n) < i, "train", np.where(np.arange(n) < j, "val", "test"))})
        print(t[t.fraud == 1].pivot_table(index="category", columns="part", values="fraud", aggfunc="count", fill_value=0)
              .sort_values("test", ascending=False).to_string())
        return

    Xtr, Xva, Xte = X.iloc[:i], X.iloc[i:j], X.iloc[j:]
    ytr, yva, yte = yv[:i], yv[i:j], yv[j:]
    keep_tr, keep_va = np.ones(i, bool), np.ones(j - i, bool)
    held = None
    if args.holdout_category:
        h = args.holdout_category
        keep_tr = ~((cats[:i] == h) & (ytr == 1))
        keep_va = ~((cats[i:j] == h) & (yva == 1))
        held = cats[j:] == h
        print(f"held-out type '{h}': removed {int((~keep_tr).sum())} train and {int((~keep_va).sum())} val frauds; "
              f"test frauds of that type = {int((held & (yte == 1)).sum())}")
    Xtr_k, ytr_k, Xva_k, yva_k = Xtr[keep_tr], ytr[keep_tr], Xva[keep_va], yva[keep_va]
    spw = float((ytr_k == 0).sum() / max((ytr_k == 1).sum(), 1))

    # --- unsupervised branch: Isolation Forest fitted on legitimate training rows only ---
    legit = Xtr_k[ytr_k == 0]
    fill = legit[ANOMALY_COLS].median()
    sample = legit.sample(min(len(legit), 200_000), random_state=SEED)
    iso = IsolationForest(n_estimators=200, max_samples=256, random_state=SEED, n_jobs=-1).fit(sample[ANOMALY_COLS].fillna(fill))
    if_score = lambda Z: -iso.score_samples(Z[ANOMALY_COLS].fillna(fill))  # higher = more anomalous
    s_tr, s_va, s_te = if_score(Xtr), if_score(Xva), if_score(Xte)
    s_va_k = s_va[keep_va]

    rows = []
    # 1) XGBoost only
    m1 = xgb(spw).fit(Xtr_k, ytr_k)
    px_va, px_te = m1.predict_proba(Xva_k)[:, 1], m1.predict_proba(Xte)[:, 1]
    t_x = best_threshold(yva_k, px_va)
    rows.append({"model": "XGBoost only", **summarize(yte, px_te >= t_x, px_te, held)})
    # 2) Isolation Forest only
    t_i = best_threshold(yva_k, s_va_k)
    rows.append({"model": "Isolation Forest only", **summarize(yte, s_te >= t_i, s_te, held)})
    # 3) OR-fusion: alert if XGB crosses its threshold OR the IF score is in the top alert-rate of validation
    t_f = float(np.quantile(s_va_k, 1 - args.if_alert_rate))
    rows.append({"model": f"OR-fusion (IF top {args.if_alert_rate:.1%})", **summarize(yte, (px_te >= t_x) | (s_te >= t_f), None, held)})
    # 4) Stacked: IF score as an extra XGBoost feature
    Xtr_s, Xva_s, Xte_s = (Z.assign(if_score=s) for Z, s in ((Xtr, s_tr), (Xva, s_va), (Xte, s_te)))
    m4 = xgb(spw).fit(Xtr_s[keep_tr], ytr_k)
    ps_va, ps_te = m4.predict_proba(Xva_s[keep_va])[:, 1], m4.predict_proba(Xte_s)[:, 1]
    t_s = best_threshold(yva_k, ps_va)
    rows.append({"model": "Stacked (IF score -> XGBoost)", **summarize(yte, ps_te >= t_s, ps_te, held)})

    tab = pd.DataFrame(rows)
    REPORTS.mkdir(exist_ok=True)
    name = f"sparkov_hybrid_holdout_{args.holdout_category}.csv" if args.holdout_category else "sparkov_hybrid.csv"
    tab.to_csv(REPORTS / name, index=False)
    print("\n", tab.to_string(index=False), f"\n\nSaved reports/{name}")


if __name__ == "__main__":
    main()
