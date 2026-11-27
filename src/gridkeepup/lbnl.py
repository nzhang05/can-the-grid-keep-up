"""ERCOT completion history from LBNL's Queued Up project-level data.

For each ERCOT interconnection request LBNL records its status at the end of 2025
(operational, active, withdrawn, suspended), dates and capacity. From that we compute:

* post-agreement shares: of capacity whose interconnection agreement (IA) was signed in
  2000-2022, how much is operating, still in progress, or withdrawn (by fuel)
* request shares: the same for all requests submitted 2000-2020
* median years from signed agreement to operation, for completed projects

Shares are capacity-weighted (``mw_1``). Suspended counts as withdrawn.

Data: LBNL, Queued Up 2026 edition data file, sheet ``03. Complete Queue Data``
(https://emp.lbl.gov/queues, CC BY 4.0). Download by hand into data/raw/lbnl/.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from gridkeepup.paths import RAW_DIR

LBNL_DIR = RAW_DIR / "lbnl"
SHEET = "03. Complete Queue Data"
IA_LAST_YEAR = 2022        # agreements old enough to have had time to finish
REQUEST_LAST_YEAR = 2020   # LBNL's own cut-off for completion rates
FUELS = {"Wind": "Wind", "Gas": "Gas", "Solar": "Solar", "Battery": "Storage"}


def latest_file(lbnl_dir: Path = LBNL_DIR) -> Path | None:
    files = sorted(lbnl_dir.glob("*.xlsx"))
    return files[-1] if files else None


def load_ercot(path: Path | None = None) -> pd.DataFrame:
    path = path or latest_file()
    if path is None:
        return pd.DataFrame()
    q = pd.read_excel(path, SHEET, header=1)
    e = q[q["region"] == "ERCOT"].copy()
    e["mw"] = pd.to_numeric(e["mw_1"], errors="coerce")
    for col in ("q_date", "ia_date", "on_date"):
        e[col] = pd.to_datetime(e[col], errors="coerce")
    e["fuel"] = e["type_clean"].map(FUELS)
    e.attrs["source_file"] = path.name
    return e


def _shares(df: pd.DataFrame) -> pd.Series:
    t = df.groupby("q_status")["mw"].sum()
    total = t.sum()
    if total == 0:
        return pd.Series({"operational": float("nan"), "active": float("nan"),
                          "withdrawn": float("nan"), "gw": 0.0})
    return pd.Series({
        "operational": t.get("operational", 0.0) / total,
        "active": t.get("active", 0.0) / total,
        "withdrawn": (t.get("withdrawn", 0.0) + t.get("suspended", 0.0)) / total,
        "gw": total / 1000,
    })


def _by_fuel(df: pd.DataFrame) -> pd.DataFrame:
    rows = {f: _shares(df[df["fuel"] == f]) for f in FUELS.values()}
    rows["All"] = _shares(df)
    return pd.DataFrame(rows).T


def post_agreement_shares(e: pd.DataFrame, ia_last_year: int = IA_LAST_YEAR) -> pd.DataFrame:
    return _by_fuel(e[e["ia_date"].notna() & (e["ia_date"].dt.year <= ia_last_year)])


def request_shares(e: pd.DataFrame, last_year: int = REQUEST_LAST_YEAR) -> pd.DataFrame:
    return _by_fuel(e[e["q_date"].dt.year <= last_year])


def agreement_to_operation_years(e: pd.DataFrame, ia_last_year: int = IA_LAST_YEAR) -> pd.Series:
    """Median years from agreement to operation, completed projects with IAs to ia_last_year.

    Recent agreements are left out: only their fastest projects have finished yet, which
    would bias the median down.
    """
    done = e[e["ia_date"].notna() & (e["ia_date"].dt.year <= ia_last_year)
             & e["on_date"].notna() & e["fuel"].notna()]
    years = (done["on_date"] - done["ia_date"]).dt.days / 365.25
    return years.groupby(done["fuel"]).median()


def odds_from_shares(shares: pd.DataFrame) -> pd.DataFrame:
    """The decided rule: low = operating, mid = + half still in progress, high = + all."""
    return pd.DataFrame({
        "low": shares["operational"],
        "mid": shares["operational"] + shares["active"] / 2,
        "high": shares["operational"] + shares["active"],
    }).round(2)


CURVE_MAX_YEARS = 12
CURVE_MIN_SAMPLE_GW = 0.5   # below this, a year's estimate is too thin: carry the last value


def completion_curve(e: pd.DataFrame, start_col: str, data_year: int = 2025,
                     max_years: int = CURVE_MAX_YEARS,
                     min_sample_gw: float = CURVE_MIN_SAMPLE_GW) -> pd.DataFrame:
    """Share of capacity online within k years of ``start_col`` (``ia_date`` or ``q_date``).

    For each k, only cohorts that have had k full years to finish are used (start year <=
    data_year - k), so recent starts never drag the curve down. Capacity-weighted. The curve
    is made non-decreasing, and a k with less than ``min_sample_gw`` of capacity repeats the
    previous value. Columns: fuel (Wind, Gas, Solar, Storage, All), k, share, sample_gw.
    """
    d = e[e[start_col].notna()].copy()
    d["start_year"] = d[start_col].dt.year
    d["years_to_online"] = (d["on_date"] - d[start_col]).dt.days / 365.25
    rows = []
    for fuel in list(FUELS.values()) + ["All"]:
        f = d if fuel == "All" else d[d["fuel"] == fuel]
        last = 0.0
        for k in range(0, max_years + 1):
            cohort = f[f["start_year"] <= data_year - k]
            sample = cohort["mw"].sum() / 1000
            if k > 0 and sample >= min_sample_gw:
                done = cohort.loc[cohort["years_to_online"] <= k, "mw"].sum() / 1000
                last = max(last, done / sample)
            rows.append({"fuel": fuel, "k": k, "share": round(last, 4),
                         "sample_gw": round(sample, 2)})
    return pd.DataFrame(rows)
