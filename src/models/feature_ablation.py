"""Sparkov: does the behavioural feature module help? XGBoost on raw columns vs raw + engineered.
Output: reports/feature_ablation.csv and reports/sparkov_feature_importance.csv
"""
import pandas as pd
from xgboost import XGBClassifier

from src.config import ROOT, REPORTS, SEED
from src.data.loaders import chrono_split, load
from src.features.behavioural import sparkov_features
from src.models.baselines import evaluate, make_xy


def main():
    df = load("sparkov")
    cache = ROOT / "data" / "processed" / f"sparkov_features_{len(df)}.parquet"
    if cache.exists():
        feats = pd.read_parquet(cache)
    else:
        print("computing features (one-off, cached afterwards)...")
        feats = sparkov_features(df)
        cache.parent.mkdir(parents=True, exist_ok=True)
        feats.to_parquet(cache)

    X_base, y = make_xy("sparkov", df)
    X_all = pd.concat([X_base, feats], axis=1)
    n = len(df)
    i, j = int(n * 0.70), int(n * 0.85)   # same chronological 70/15/15 as the baselines
    spw = float((y.iloc[:i] == 0).sum() / (y.iloc[:i] == 1).sum())

    def xgb():
        return XGBClassifier(n_estimators=300, max_depth=6, learning_rate=0.1, subsample=0.8, colsample_bytree=0.8,
                             scale_pos_weight=spw, tree_method="hist", eval_metric="aucpr", n_jobs=-1, random_state=SEED)

    rows, last = [], None
    for name, X in [("XGBoost raw columns", X_base), ("XGBoost raw + behavioural", X_all)]:
        m = xgb()
        res = evaluate(m, X.iloc[:i], y.iloc[:i], X.iloc[i:j], y.iloc[i:j], X.iloc[j:], y.iloc[j:])
        print(f"{name}: {res}")
        rows.append({"model": name, **res})
        last = (m, X.columns)
    REPORTS.mkdir(exist_ok=True)
    tab = pd.DataFrame(rows)
    tab.to_csv(REPORTS / "feature_ablation.csv", index=False)
    imp = pd.Series(last[0].feature_importances_, index=last[1]).sort_values(ascending=False)
    imp.to_csv(REPORTS / "sparkov_feature_importance.csv", header=["importance"])
    print("\n", tab.to_string(index=False))
    print("\nTop features:\n", imp.head(12).round(4).to_string())


if __name__ == "__main__":
    main()
