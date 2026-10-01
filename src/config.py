import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = Path(os.environ.get("FRAUD_DATA_DIR", ROOT / "data" / "raw"))
REPORTS = ROOT / "reports"
SEED = 42

# (target column, time column) per dataset
SCHEMA = {
    "sparkov": ("is_fraud", "trans_date_trans_time"),
    "ulb": ("Class", "Time"),
    "ieee": ("isFraud", "TransactionDT"),
}
