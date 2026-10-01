"""Sparkov feature matrix (raw columns + behavioural features), cached to data/processed/."""
import pandas as pd

from src.config import ROOT
from src.data.loaders import load
from src.features.behavioural import sparkov_features
from src.models.baselines import make_xy


def get_sparkov_matrix():
    df = load("sparkov")  # sorted chronologically
    cache = ROOT / "data" / "processed" / f"sparkov_features_{len(df)}.parquet"
    if cache.exists():
        feats = pd.read_parquet(cache)
    else:
        print("computing behavioural features (one-off, cached afterwards)...")
        feats = sparkov_features(df)
        cache.parent.mkdir(parents=True, exist_ok=True)
        feats.to_parquet(cache)
    X_base, y = make_xy("sparkov", df)
    return pd.concat([X_base, feats], axis=1), y, df
