"""Dataset loaders + chronological (time-based) splitting.

Expected layout under data/raw/:
  sparkov/fraudTrain.csv, sparkov/fraudTest.csv
  ulb/creditcard.csv
  ieee/train_transaction.csv, ieee/train_identity.csv
"""
import pandas as pd

from src.config import RAW, SCHEMA


def load_sparkov() -> pd.DataFrame:
    parts = [pd.read_csv(RAW / "sparkov" / f, index_col=0) for f in ("fraudTrain.csv", "fraudTest.csv")]
    df = pd.concat(parts, ignore_index=True)
    df["trans_date_trans_time"] = pd.to_datetime(df["trans_date_trans_time"])
    df["dob"] = pd.to_datetime(df["dob"])
    return df


def load_ulb() -> pd.DataFrame:
    return pd.read_csv(RAW / "ulb" / "creditcard.csv")


def load_ieee() -> pd.DataFrame:
    tx = pd.read_csv(RAW / "ieee" / "train_transaction.csv")
    idn = pd.read_csv(RAW / "ieee" / "train_identity.csv")
    return tx.merge(idn, on="TransactionID", how="left")


LOADERS = {"sparkov": load_sparkov, "ulb": load_ulb, "ieee": load_ieee}


def load(name: str) -> pd.DataFrame:
    df = LOADERS[name]()
    _, time_col = SCHEMA[name]
    return df.sort_values(time_col, kind="stable").reset_index(drop=True)


def chrono_split(df: pd.DataFrame, val_frac: float = 0.15, test_frac: float = 0.15):
    """df must already be sorted by time. Earlier rows -> train, latest -> test (no shuffling)."""
    n = len(df)
    i = int(n * (1 - val_frac - test_frac))
    j = int(n * (1 - test_frac))
    return df.iloc[:i], df.iloc[i:j], df.iloc[j:]
