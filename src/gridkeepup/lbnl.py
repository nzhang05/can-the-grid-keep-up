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
