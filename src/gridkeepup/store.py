"""Load raw and manual inputs into one DuckDB file the models and dashboard read from."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from gridkeepup import clean, manual
from gridkeepup.fetch import eia860m, eia930
from gridkeepup.paths import DB_PATH


def _write(con: duckdb.DuckDBPyConnection, table: str, df: pd.DataFrame) -> None:
    con.register("_df", df)
    con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM _df")
    con.unregister("_df")
    print(f"  {table}: {len(df):,} rows")


def build(db_path: Path = DB_PATH) -> dict[str, int]:
    """(Re)build every table from whatever inputs are on disk. Missing sources are skipped."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    with duckdb.connect(str(db_path)) as con:
        demand_raw, fuel_raw = eia930.load("demand"), eia930.load("fuel_mix")
        tables: dict[str, pd.DataFrame] = {
            "large_load_queue": manual.large_load_queue(),
            "large_load_stages": manual.large_load_stages(),
            "reference": manual.load("ercot_reference"),
            "eia930_demand": demand_raw,
            "eia930_fuel_mix": fuel_raw,
            "demand_clean": clean.clean_demand(demand_raw),
            "generation_clean": clean.clean_generation(fuel_raw),
        }
        tables.update({f"eia860m_{k}": v for k, v in eia860m.load_latest().items()})
        for name, df in tables.items():
            if df.empty:
                print(f"  {name}: no input yet, skipped")
                continue
            _write(con, name, df)
            counts[name] = len(df)
    return counts


def query(sql: str, db_path: Path = DB_PATH) -> pd.DataFrame:
    with duckdb.connect(str(db_path), read_only=True) as con:
        return con.execute(sql).df()
