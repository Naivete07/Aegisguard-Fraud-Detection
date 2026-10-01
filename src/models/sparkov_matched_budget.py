"""Exact equal-alert-budget comparison for the held-out fraud-type experiment (v2).

v1 matched budgets with validation-quantile thresholds, which drift on the test slice, so the "same alerts"
rows did not actually have the same number of alerts. v2 fixes the budget exactly: every method may raise
exactly K alerts on the test slice (top-K by score), K = budget x number of test transactions.

Methods at each budget K:
  XGBoost top-K                 all K alerts from the supervised score
  IF top-K                      all K alerts from the Isolation Forest score
  Tiered q                      (1-q)K alerts from XGBoost, then the IF fills the remaining qK with its
                                highest-scoring transactions not already flagged  (= PRD approve/review/block idea)

  python -m src.models.sparkov_matched_budget --holdout-category grocery_pos shopping_net misc_net
"""
import argparse

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from src.config import REPORTS, SEED
from src.models.sparkov_data import get_sparkov_matrix
from src.models.sparkov_hybrid import ANOMALY_COLS, summarize, xgb

BUDGETS = [0.0025, 0.005, 0.01, 0.02]  # alerts as a share of test transactions
QS = [0.10, 0.25, 0.50]                # share of the budget reserved for the IF queue


def topk_mask(score, k):
    m = np.zeros(len(score), bool)
    if k > 0:
        m[np.argpartition(-score, k - 1)[:k]] = True
    return m


def tiered(px, s, k, q):
    k_if = int(round(q * k))
    m = topk_mask(px, k - k_if)
    m |= topk_mask(np.where(m, -np.inf, s), k_if)
    return m


def run(cat, X, y, cats):
    n = len(y); i, j = int(n * 0.70), int(n * 0.85); yv = y.to_numpy()
    Xtr, Xte = X.iloc[:i], X.iloc[j:]
    ytr, yte = yv[:i], yv[j:]
    keep = ~((cats[:i] == cat) & (ytr == 1))
    held = cats[j:] == cat
    Xtr_k, ytr_k = Xtr[keep], ytr[keep]
    spw = float((ytr_k == 0).sum() / max((ytr_k == 1).sum(), 1))

    legit = Xtr_k[ytr_k == 0]; fill = legit[ANOMALY_COLS].median()
    sample = legit.sample(min(len(legit), 200_000), random_state=SEED)
    iso = IsolationForest(n_estimators=200, max_samples=256, random_state=SEED, n_jobs=-1).fit(sample[ANOMALY_COLS].fillna(fill))
    s_te = -iso.score_samples(Xte[ANOMALY_COLS].fillna(fill))
    px_te = xgb(spw).fit(Xtr_k, ytr_k).predict_proba(Xte)[:, 1]

    rows = []
    for b in BUDGETS:
        k = int(round(b * len(yte)))
        cands = [("XGBoost top-K", topk_mask(px_te, k)), ("IF top-K", topk_mask(s_te, k))]
        cands += [(f"Tiered: {int(q*100)}% of budget to IF", tiered(px_te, s_te, k, q)) for q in QS]
        for name, pred in cands:
            rows.append({"holdout": cat, "budget": f"{b:.2%}", "model": name, **summarize(yte, pred, None, held)})
    return pd.DataFrame(rows).drop(columns=["pr_auc", "n_heldout_test_fraud"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdout-category", nargs="+", required=True)
    args = ap.parse_args()
    X, y, df = get_sparkov_matrix()
    cats = df["category"].to_numpy()
    out = []
    for c in args.holdout_category:
        t = run(c, X, y, cats); out.append(t)
        print(f"\n=== held-out: {c} ===")
        print(t.drop(columns=["holdout"]).to_string(index=False))
    REPORTS.mkdir(exist_ok=True)
    pd.concat(out).to_csv(REPORTS / "sparkov_matched_budget_v2.csv", index=False)
    print("\nSaved reports/sparkov_matched_budget_v2.csv")


if __name__ == "__main__":
    main()
