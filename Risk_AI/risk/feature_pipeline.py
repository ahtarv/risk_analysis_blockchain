

from __future__ import annotations

import time
from typing import Optional

import pandas as pd

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False
    print("[FeaturePipeline] WARNING: duckdb not installed. "
          "Run: pip install duckdb")

_SCHEMA_SQL = 

_FEATURE_SQL = 

def _pandas_rolling_features(df: pd.DataFrame) -> pd.DataFrame:

    df = df.copy().sort_values("submit_us").reset_index(drop=True)

    df["submit_s"] = pd.to_datetime(df["submit_us"], unit="us")
    df = df.set_index("submit_s")

    df["is_cancelled"]     = (df["cancel_us"] > 0) & (~df["filled"])
    df["is_spoof_cand"]    = (
        df["is_cancelled"] &
        (df["depth_level"] <= 2) &
        (df["lifetime_us"] <= 200_000)
    )

    windows = {"1m": "1min", "5m": "5min", "1h": "60min"}
    result_parts = {}

    for tag, window in windows.items():
        r = df.rolling(window, min_periods=1)
        result_parts[f"orders_{tag}"]       = r["order_id"].count()
        result_parts[f"fills_{tag}"]        = r["filled"].sum()
        result_parts[f"cancels_{tag}"]      = r["is_cancelled"].sum()
        result_parts[f"spoofs_{tag}"]       = r["is_spoof_cand"].sum()
        result_parts[f"avg_lt_us_{tag}"]    = r["lifetime_us"].mean()
        result_parts[f"std_lt_us_{tag}"]    = r["lifetime_us"].std()

    feat = pd.DataFrame(result_parts, index=df.index)

    def safe_div(a: pd.Series, b: pd.Series, fallback: pd.Series) -> pd.Series:
        return a.where(b <= 0, a / b.clip(lower=1)).fillna(fallback)

    for tag in ["1m", "5m", "1h"]:
        feat[f"otr_{tag}"] = safe_div(
            feat[f"orders_{tag}"], feat[f"fills_{tag}"], feat[f"orders_{tag}"])
        if tag != "1h":
            feat[f"cfr_{tag}"] = safe_div(
                feat[f"cancels_{tag}"], feat[f"fills_{tag}"], feat[f"cancels_{tag}"])
            feat[f"spoof_ratio_{tag}"] = safe_div(
                feat[f"spoofs_{tag}"], feat[f"cancels_{tag}"],
                pd.Series(0.0, index=feat.index))

    std_1h = feat["std_lt_us_1h"].fillna(1.0).clip(lower=1.0)
    feat["lifetime_zscore"] = (
        (feat["avg_lt_us_1m"] - feat["avg_lt_us_1h"]) / std_1h
    ).fillna(0.0)

    out = df[["order_id", "submit_us", "is_anomaly", "label"]].copy()
    out = pd.concat([out.reset_index(drop=True), feat.reset_index(drop=True)], axis=1)
    return out

class FeaturePipeline:

    def __init__(self, db_path: str = ":memory:", use_pandas_fallback: bool = False):
        self.db_path = db_path
        self._use_pandas = use_pandas_fallback or not DUCKDB_AVAILABLE
        self._con = None
        self._df_buffer: Optional[pd.DataFrame] = None

        if not self._use_pandas:
            self._con = duckdb.connect(db_path)
            self._con.execute(_SCHEMA_SQL)

    def ingest(self, df: pd.DataFrame) -> None:

        if self._use_pandas:
            self._df_buffer = df
        else:

            self._con.register("_staging", df)
            self._con.execute(
                "INSERT INTO order_events SELECT * FROM _staging"
            )

    def compute(self) -> pd.DataFrame:

        if self._use_pandas:
            if self._df_buffer is None:
                raise RuntimeError("No data ingested yet. Call ingest() first.")
            return _pandas_rolling_features(self._df_buffer)
        else:
            return self._con.execute(_FEATURE_SQL).df()

    def query(self, sql: str) -> pd.DataFrame:

        if self._use_pandas:
            raise RuntimeError("query() requires DuckDB. Use compute() instead.")
        return self._con.execute(sql).df()

    def row_count(self) -> int:

        if self._use_pandas:
            return len(self._df_buffer) if self._df_buffer is not None else 0
        return self._con.execute("SELECT COUNT(*) FROM order_events").fetchone()[0]

    def close(self) -> None:
        if self._con is not None:
            self._con.close()
            self._con = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
