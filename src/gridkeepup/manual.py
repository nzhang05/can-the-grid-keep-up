"""Hand-entered inputs in data/manual/, each row with a source URL and a verified flag."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from gridkeepup.paths import MANUAL_DIR

REQUIRED = {
    "ercot_large_load_queue": ["as_of_month", "total_large_load_gw", "source", "url", "verified"],
    "ercot_large_load_stages": ["as_of_month", "stage", "gw", "source", "url", "verified"],
    "ercot_reference": ["metric", "value", "unit", "source", "url", "verified"],
}


def load(name: str, manual_dir: Path = MANUAL_DIR) -> pd.DataFrame:
    df = pd.read_csv(manual_dir / f"{name}.csv")
    missing = [c for c in REQUIRED[name] if c not in df.columns]
    if missing:
        raise ValueError(f"{name}.csv is missing columns {missing}")
    if df["url"].isna().any():
        raise ValueError(f"{name}.csv has rows without a source URL")
    if "as_of_month" in df.columns:
        df["as_of"] = pd.to_datetime(df["as_of_month"], format="%Y-%m")
    return df


def large_load_queue() -> pd.DataFrame:
    return load("ercot_large_load_queue").sort_values("as_of").reset_index(drop=True)


def large_load_stages() -> pd.DataFrame:
    return load("ercot_large_load_stages")


def reference(metric: str) -> float:
    df = load("ercot_reference")
    row = df.loc[df["metric"] == metric]
    if row.empty:
        raise KeyError(metric)
    return float(row["value"].iloc[0])


def reference_date(metric: str) -> pd.Timestamp:
    df = load("ercot_reference")
    return pd.Timestamp(df.loc[df["metric"] == metric, "date"].iloc[0])


def unverified_count() -> int:
    return int(sum((~load(name)["verified"].astype(bool)).sum() for name in REQUIRED))
