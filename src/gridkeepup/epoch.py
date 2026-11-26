"""Bottom-up cross-check: Epoch AI's frontier AI data centers in Texas vs the demand model.

Epoch tracks only the largest AI campuses (12 Texas sites in the Nov 2026 download), so
its total is a *subset* of all data center load: the model should sit at or above it.

Epoch's timeline ``Power (MW)`` is facility power (about 1.3x IT power). It is not the
same as grid demand: hybrid campuses with on-site generation (Stargate Abilene has about
1 GW of on-site gas) can draw much less from the grid, especially at peak.

Data: Epoch AI, 'AI data centers', https://epoch.ai/data/ai-data-centers (CC BY 4.0).
Download by hand into data/raw/epoch/data_centers/.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from gridkeepup import config, demand
from gridkeepup.paths import RAW_DIR

EPOCH_DIR = RAW_DIR / "epoch" / "data_centers"
TEXAS = r"\bTX\b|Texas"


def load(epoch_dir: Path = EPOCH_DIR) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(sites, timelines). Empty frames if the download isn't there."""
    sites_path, tl_path = epoch_dir / "data_centers.csv", epoch_dir / "data_center_timelines.csv"
    if not (sites_path.exists() and tl_path.exists()):
        return pd.DataFrame(), pd.DataFrame()
    return pd.read_csv(sites_path), pd.read_csv(tl_path, parse_dates=["Date"])


def texas_sites(sites: pd.DataFrame) -> pd.DataFrame:
    return sites[sites["Address"].fillna("").str.contains(TEXAS, regex=True)].copy()


def facility_gw_asof(timelines: pd.DataFrame, names: set[str], asof: pd.Timestamp) -> float:
    """Sum of each site's latest facility power on or before ``asof`` (planned dates count)."""
    sub = timelines[(timelines["Date"] <= asof) & timelines["Data center"].isin(names)]
    return float(sub.sort_values("Date").groupby("Data center")["Power (MW)"].last().sum()) / 1000


def compare(sites: pd.DataFrame | None = None, timelines: pd.DataFrame | None = None,
            proj: pd.DataFrame | None = None, cfg: dict | None = None) -> pd.DataFrame:
    """Per year: Epoch's new Texas facility power since the pause vs the model's ramped GW."""
    cfg = cfg or config.assumptions()
    if sites is None or timelines is None:
        sites, timelines = load()
    if sites.empty:
        return pd.DataFrame()
    proj = demand.project() if proj is None else proj
    since = pd.Timestamp(cfg["crosscheck"]["epoch_since"])
    tx = set(texas_sites(sites)["Name"])
    likely = tx - set(cfg["crosscheck"]["epoch_possibly_not_ercot"])
    model = proj.pivot(index="year", columns="scenario", values="ramped_gw")
    rows = []
    for year in model.index:
        end = pd.Timestamp(f"{year}-12-31")
        rows.append({
            "year": year,
            "epoch_tx_all_gw": facility_gw_asof(timelines, tx, end)
            - facility_gw_asof(timelines, tx, since),
            "epoch_tx_likely_ercot_gw": facility_gw_asof(timelines, likely, end)
            - facility_gw_asof(timelines, likely, since),
            **{f"model_{s}_gw": model.loc[year, s] for s in demand.SCENARIOS},
        })
    out = pd.DataFrame(rows)
    out["model_high_covers_epoch"] = out["model_high_gw"] >= out["epoch_tx_likely_ercot_gw"]
    out["epoch_timelines_end"] = timelines["Date"].max().date()
    return out.round(2)
