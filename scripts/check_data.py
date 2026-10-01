"""Step 1 sanity check: are the datasets where the code expects them, and what do they look like?"""
import sys

from src.config import SCHEMA
from src.data.loaders import load


def main(names):
    for name in names:
        target, time_col = SCHEMA[name]
        try:
            df = load(name)
        except FileNotFoundError as e:
            print(f"[{name}] MISSING: {e}")
            continue
        y = df[target]
        print(f"\n=== {name} ===")
        print(f"rows={len(df):,}  cols={df.shape[1]}")
        print(f"fraud={int(y.sum()):,}  rate={y.mean():.4%}")
        print(f"time range: {df[time_col].min()} -> {df[time_col].max()}")
        miss = df.isna().mean().sort_values(ascending=False).head(3)
        print("top missing cols:", {k: f"{v:.1%}" for k, v in miss.items()})


if __name__ == "__main__":
    main(sys.argv[1:] or list(SCHEMA))
