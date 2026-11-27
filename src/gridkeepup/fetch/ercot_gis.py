"""ERCOT Generator Interconnection Status (GIS) report: the interconnection queue.

Monthly Excel report from https://www.ercot.com/gridinfo/resource ("Monthly Generator
Interconnection Status Report", file "GIS REPORT <month> <year>"). Download by hand into
data/raw/ercot_gis/; the newest file there is used.

We read the "Project Details - Large Gen" sheet: one row per project for which a Full
Interconnection Study has been requested (inactive projects excluded by ERCOT), with fuel,
nameplate MW, projected commercial operation date (COD) and milestone dates.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from gridkeepup.paths import RAW_DIR

GIS_DIR = RAW_DIR / "ercot_gis"
SHEET = "Project Details - Large Gen"

# ERCOT fuel codes -> model fuel groups. "OTH" is batteries when technology is "BA".
FUEL_CODES = {"GAS": "Gas", "SOL": "Solar", "WIN": "Wind", "NUC": "Nuclear", "HYD": "Hydro",
              "WAT": "Hydro", "OIL": "Other"}
STAGES = ("synchronized", "energized", "construction", "signed", "study")


def latest_file(gis_dir: Path = GIS_DIR) -> Path | None:
    files = sorted(gis_dir.glob("*.xlsx"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def fuel_group(fuel: str, technology: str) -> str:
    fuel, technology = str(fuel).strip(), str(technology).strip()
    if fuel == "OTH":
        return "Storage" if technology == "BA" else "Other"
    return FUEL_CODES.get(fuel, "Other")


def stage(row: pd.Series) -> str:
    """Furthest milestone reached: synchronized > energized > construction > signed > study."""
    if pd.notna(row["Approved for Synchronization"]):
        return "synchronized"
    if pd.notna(row["Approved for Energization"]):
        return "energized"
    if pd.notna(row["Construction Start"]):
        return "construction"
    if pd.notna(row["IA Signed"]):
        return "signed"
    return "study"


def read_projects(path: Path) -> pd.DataFrame:
    raw = pd.read_excel(path, SHEET, header=None)
    header = next(i for i, r in raw.iterrows()
                  if (r.astype(str).str.strip() == "INR").any()
                  and (r.astype(str).str.strip() == "Fuel").any())
    df = raw.iloc[header + 1:].copy()
    df.columns = [str(c).strip() for c in raw.iloc[header]]
    df = df[df["INR"].notna() & df["Fuel"].notna()]
    for col in ("Projected COD", "IA Signed", "Construction Start", "Approved for Energization",
                "Approved for Synchronization"):
        df[col] = pd.to_datetime(df[col], errors="coerce")
    out = pd.DataFrame({
        "inr": df["INR"].astype(str),
        "project_name": df["Project Name"].astype(str),
        "county": df["County"].astype(str).str.strip(),
        "fuel": [fuel_group(f, t) for f, t in zip(df["Fuel"], df["Technology"], strict=True)],
        "stage": df.apply(stage, axis=1),
        "cod_year": df["Projected COD"].dt.year,
        "mw_nameplate": pd.to_numeric(df["Capacity (MW)"], errors="coerce").fillna(0.0),
    })
    out.attrs["source_file"] = path.name
    return out.reset_index(drop=True)


def load_latest(gis_dir: Path = GIS_DIR) -> pd.DataFrame:
    path = latest_file(gis_dir)
    return read_projects(path) if path else pd.DataFrame()
