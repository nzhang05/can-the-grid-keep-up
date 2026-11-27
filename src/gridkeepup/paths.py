"""Where everything lives on disk. All paths are relative to the repo root."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"          # downloaded files (git-ignored)
MANUAL_DIR = DATA_DIR / "manual"    # hand-entered inputs with sources (committed)
PROCESSED_DIR = DATA_DIR / "processed"
DERIVED_DIR = DATA_DIR / "derived"      # tables computed from raw data (committed)
DB_PATH = DATA_DIR / "grid.duckdb"
OUTPUTS_DIR = ROOT / "outputs"

EIA930_DIR = RAW_DIR / "eia930"
EIA860M_DIR = RAW_DIR / "eia860m"
