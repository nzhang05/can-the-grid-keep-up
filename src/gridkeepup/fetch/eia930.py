"""EIA-930 Hourly Electric Grid Monitor, via the EIA API v2.

Two series for ERCOT (EIA respondent code ``ERCO``):

* hourly demand (``electricity/rto/region-data``, type ``D``)
* hourly net generation by fuel (``electricity/rto/fuel-type-data``)

Values are MWh per hour, i.e. average MW over the hour. Timestamps are UTC
(EIA's ``hourly`` frequency); the period label marks the hour's start.

Docs: https://www.eia.gov/opendata/documentation.php
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import requests

from gridkeepup.paths import EIA930_DIR

API_BASE = "https://api.eia.gov/v2"
PAGE_SIZE = 5000  # EIA API v2 maximum rows per request

DEMAND_ROUTE = "electricity/rto/region-data"
FUEL_ROUTE = "electricity/rto/fuel-type-data"


def _get_json(session: requests.Session, url: str, params: dict, retries: int = 4) -> dict:
    for attempt in range(retries):
        resp = session.get(url, params=params, timeout=60)
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries - 1:
            time.sleep(2**attempt)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("unreachable")


def fetch_route(
    route: str,
    facets: dict[str, list[str]],
    start: str,
    end: str,
    api_key: str,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """Download every hourly row of ``route`` between ``start`` and ``end``.

    ``start``/``end`` use EIA's hourly format, e.g. ``"2024-01-01T00"``.
    """
    session = session or requests.Session()
    url = f"{API_BASE}/{route}/data/"
    base_params: dict[str, object] = {
        "api_key": api_key,
        "frequency": "hourly",
        "data[0]": "value",
        "start": start,
        "end": end,
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "length": PAGE_SIZE,
    }
    for name, values in facets.items():
        base_params[f"facets[{name}][]"] = values

    rows: list[dict] = []
    offset = 0
    while True:
        payload = _get_json(session, url, {**base_params, "offset": offset})
        response = payload.get("response", {})
        page = response.get("data", [])
        rows.extend(page)
        total = int(response.get("total", 0) or 0)
        offset += len(page)
        if not page or offset >= total:
            break
    return parse_rows(rows)


def parse_rows(rows: list[dict]) -> pd.DataFrame:
    """Turn EIA API rows into a tidy frame with a UTC timestamp and numeric value."""
    if not rows:
        return pd.DataFrame(columns=["timestamp_utc", "value_mwh"])
    df = pd.DataFrame(rows)
    df["timestamp_utc"] = pd.to_datetime(df["period"], format="%Y-%m-%dT%H", utc=True)
    df["value_mwh"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.drop(columns=["period", "value"])
    df.columns = [c.replace("-", "_") for c in df.columns]
    lead = ["timestamp_utc", "value_mwh"]
    return df[lead + [c for c in df.columns if c not in lead]]


def fetch_demand_year(year: int, api_key: str, respondent: str = "ERCO",
                      session: requests.Session | None = None) -> pd.DataFrame:
    return fetch_route(
        DEMAND_ROUTE,
        {"respondent": [respondent], "type": ["D"]},
        f"{year}-01-01T00",
        f"{year}-12-31T23",
        api_key,
        session,
    )


def fetch_fuel_mix_year(year: int, api_key: str, respondent: str = "ERCO",
                        session: requests.Session | None = None) -> pd.DataFrame:
    return fetch_route(
        FUEL_ROUTE,
        {"respondent": [respondent]},
        f"{year}-01-01T00",
        f"{year}-12-31T23",
        api_key,
        session,
    )


def download(first_year: int, last_year: int, api_key: str, respondent: str = "ERCO",
             out_dir: Path = EIA930_DIR, overwrite: bool = False) -> list[Path]:
    """Save one CSV per series per year. Skips years already on disk unless ``overwrite``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    written: list[Path] = []
    for year in range(first_year, last_year + 1):
        for name, fn in (("demand", fetch_demand_year), ("fuel_mix", fetch_fuel_mix_year)):
            path = out_dir / f"{name}_{respondent}_{year}.csv"
            if path.exists() and not overwrite:
                print(f"  skip {path.name} (exists)")
                continue
            df = fn(year, api_key, respondent, session)
            df.to_csv(path, index=False)
            print(f"  wrote {path.name}: {len(df):,} rows")
            written.append(path)
    return written


def load(name: str, respondent: str = "ERCO", raw_dir: Path = EIA930_DIR) -> pd.DataFrame:
    """Load all downloaded years of ``name`` ('demand' or 'fuel_mix')."""
    files = sorted(raw_dir.glob(f"{name}_{respondent}_*.csv"))
    if not files:
        return pd.DataFrame()
    df = pd.concat((pd.read_csv(f) for f in files), ignore_index=True)
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    return df.drop_duplicates().sort_values("timestamp_utc").reset_index(drop=True)
