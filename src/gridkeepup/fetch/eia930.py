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
TIMEOUT_S = 120
RETRIES = 8          # waits 2, 4, 8, 16, 32, 60, 60 s: about 3 minutes before giving up
MAX_WAIT_S = 60
RETRY_STATUS = (429, 500, 502, 503, 504)

DEMAND_ROUTE = "electricity/rto/region-data"
FUEL_ROUTE = "electricity/rto/fuel-type-data"


class EIAError(RuntimeError):
    """An EIA API failure. The message never contains the request URL (it holds your key)."""


def _describe(params: dict) -> str:
    start, end = params.get("start", "?"), params.get("end", "?")
    return f"{start} to {end}, offset {params.get('offset', 0)}"


def _get_json(session: requests.Session, url: str, params: dict,
              retries: int = RETRIES, sleep=time.sleep) -> dict:
    """GET with retries on timeouts, dropped connections and 429/5xx (EIA's API is slow).

    Errors are re-raised as ``EIAError`` without the URL, so the API key is never printed.
    """
    problem = ""
    for attempt in range(retries):
        try:
            resp = session.get(url, params=params, timeout=TIMEOUT_S)
        except (requests.Timeout, requests.ConnectionError) as e:
            problem = type(e).__name__
        else:
            if resp.status_code not in RETRY_STATUS:
                if not resp.ok:
                    raise EIAError(f"EIA API returned HTTP {resp.status_code} for "
                                   f"{_describe(params)}") from None
                return resp.json()
            problem = f"HTTP {resp.status_code}"
        if attempt < retries - 1:
            wait = min(2 ** (attempt + 1), MAX_WAIT_S)
            print(f"    EIA API: {problem}, retrying in {wait}s...")
            sleep(wait)
    raise EIAError(f"EIA API still failing after {retries} tries ({problem}) for "
                   f"{_describe(params)}") from None


def month_windows(year: int) -> list[tuple[str, str]]:
    """(start, end) hourly bounds per month, e.g. ('2024-02-01T00', '2024-02-29T23')."""
    out = []
    for month in range(1, 13):
        start = pd.Timestamp(year=year, month=month, day=1)
        end = start + pd.offsets.MonthEnd(0)
        out.append((f"{start:%Y-%m-%d}T00", f"{end:%Y-%m-%d}T23"))
    return out


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


def _fetch_year_by_month(route: str, facets: dict[str, list[str]], year: int, api_key: str,
                         session: requests.Session | None) -> pd.DataFrame:
    """One request series per month: small queries finish well inside EIA's timeouts."""
    frames = []
    for start, end in month_windows(year):
        frames.append(fetch_route(route, facets, start, end, api_key, session))
        print(f"    {start[:7]} done", end="\r", flush=True)
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else parse_rows([])


def fetch_demand_year(year: int, api_key: str, respondent: str = "ERCO",
                      session: requests.Session | None = None) -> pd.DataFrame:
    return _fetch_year_by_month(DEMAND_ROUTE, {"respondent": [respondent], "type": ["D"]},
                                year, api_key, session)


def fetch_fuel_mix_year(year: int, api_key: str, respondent: str = "ERCO",
                        session: requests.Session | None = None) -> pd.DataFrame:
    return _fetch_year_by_month(FUEL_ROUTE, {"respondent": [respondent]},
                                year, api_key, session)


def download(first_year: int, last_year: int, api_key: str, respondent: str = "ERCO",
             out_dir: Path = EIA930_DIR, overwrite: bool = False) -> list[str]:
    """Save one CSV per series per year. Skips years already on disk unless ``overwrite``.

    A year that keeps failing is skipped (not written) and the rest carry on; rerun to
    fill the gaps. Returns the names of files that could not be fetched.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    failed: list[str] = []
    for year in range(first_year, last_year + 1):
        for name, fn in (("demand", fetch_demand_year), ("fuel_mix", fetch_fuel_mix_year)):
            path = out_dir / f"{name}_{respondent}_{year}.csv"
            if path.exists() and not overwrite:
                print(f"  skip {path.name} (exists)")
                continue
            print(f"  fetching {path.name}...")
            try:
                df = fn(year, api_key, respondent, session)
            except EIAError as e:
                print(f"  FAILED {path.name}: {e}")
                failed.append(path.name)
                continue
            # Write only complete years, so an interrupted run resumes where it stopped.
            df.to_csv(path, index=False)
            print(f"  wrote {path.name}: {len(df):,} rows")
    if failed:
        print(f"  {len(failed)} file(s) not fetched; rerun `gridkeepup fetch eia930` later.")
    return failed


def load(name: str, respondent: str = "ERCO", raw_dir: Path = EIA930_DIR) -> pd.DataFrame:
    """Load all downloaded years of ``name`` ('demand' or 'fuel_mix')."""
    files = sorted(raw_dir.glob(f"{name}_{respondent}_*.csv"))
    if not files:
        return pd.DataFrame()
    df = pd.concat((pd.read_csv(f) for f in files), ignore_index=True)
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    return df.drop_duplicates().sort_values("timestamp_utc").reset_index(drop=True)
