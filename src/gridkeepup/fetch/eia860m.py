"""EIA-860M Preliminary Monthly Electric Generator Inventory.

One Excel workbook per month with sheets for operating, planned and retired
generators. We keep the generators in the ERCOT balancing area.

Page: https://www.eia.gov/electricity/data/eia860m/

If the automatic download fails (EIA sometimes renames files), download the
latest workbook by hand and drop it into data/raw/eia860m/; ``load_latest``
picks up the newest .xlsx in that folder.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pandas as pd
import requests

from gridkeepup.paths import EIA860M_DIR

BASE = "https://www.eia.gov/electricity/data/eia860m"
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december"]
SHEETS = {"operating": "Operating", "planned": "Planned", "retired": "Retired"}
HEADER_MARKER = "Entity ID"


def candidate_urls(today: dt.date, months_back: int = 6) -> list[tuple[str, str]]:
    """(filename, url) pairs to try, newest month first."""
    out = []
    year, month = today.year, today.month
    for _ in range(months_back):
        name = f"{MONTHS[month - 1]}_generator{year}.xlsx"
        out.append((name, f"{BASE}/xls/{name}"))
        out.append((name, f"{BASE}/archive/xls/{name}"))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return out


def download_latest(out_dir: Path = EIA860M_DIR, today: dt.date | None = None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    today = today or dt.date.today()
    tried = []
    for name, url in candidate_urls(today):
        resp = requests.get(url, timeout=120)
        tried.append(f"{url} -> {resp.status_code}")
        content_type = resp.headers.get("content-type", "")
        if resp.ok and "html" not in content_type:
            path = out_dir / name
            path.write_bytes(resp.content)
            print(f"  wrote {path.name} ({len(resp.content) / 1e6:.1f} MB)")
            return path
    raise RuntimeError(
        "Could not find a recent EIA-860M workbook. Download it by hand from "
        f"{BASE}/ into {out_dir}.\nTried:\n  " + "\n  ".join(tried)
    )


def _snake(name: str) -> str:
    name = re.sub(r"\(([^)]*)\)", r"\1", str(name)).strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", name).strip("_")


def read_sheet(path: Path, sheet: str) -> pd.DataFrame:
    """Read one sheet, finding the header row (EIA puts notes above it)."""
    preview = pd.read_excel(path, sheet_name=sheet, header=None, nrows=15)
    header_row = next(
        (i for i, row in preview.iterrows()
         if any(str(v).strip() == HEADER_MARKER for v in row.values)),
        None,
    )
    if header_row is None:
        raise ValueError(f"No '{HEADER_MARKER}' header found in sheet {sheet!r} of {path.name}")
    df = pd.read_excel(path, sheet_name=sheet, header=header_row)
    df.columns = [_snake(c) for c in df.columns]
    # Drop footnote rows at the bottom (no generator ID).
    if "generator_id" in df.columns:
        df = df[df["generator_id"].notna()]
    return df.reset_index(drop=True)


def filter_region(df: pd.DataFrame, balancing_authority: str = "ERCO") -> pd.DataFrame:
    col = "balancing_authority_code"
    if col not in df.columns:
        raise KeyError(f"Column {col!r} missing; columns are {list(df.columns)}")
    return df[df[col].astype(str).str.strip() == balancing_authority].reset_index(drop=True)


def latest_file(raw_dir: Path = EIA860M_DIR) -> Path | None:
    files = sorted(raw_dir.glob("*.xlsx"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def load_latest(balancing_authority: str = "ERCO",
                raw_dir: Path = EIA860M_DIR) -> dict[str, pd.DataFrame]:
    path = latest_file(raw_dir)
    if path is None:
        return {}
    out = {}
    for key, sheet in SHEETS.items():
        df = filter_region(read_sheet(path, sheet), balancing_authority)
        df["source_file"] = path.name
        out[key] = df
    return out
