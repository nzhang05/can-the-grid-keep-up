"""Settings: API keys from `.env`, modelling assumptions from `config/assumptions.yaml`."""

import os
from functools import lru_cache
from typing import Any

import yaml
from dotenv import load_dotenv

from gridkeepup.paths import CONFIG_DIR, ROOT


class MissingKeyError(RuntimeError):
    """Raised when a required API key is not set."""


def load_env() -> None:
    """Load `.env` from the repo root, if present. Existing env vars win."""
    load_dotenv(ROOT / ".env", override=False)


def get_eia_api_key() -> str:
    load_env()
    key = os.getenv("EIA_API_KEY", "").strip()
    if not key:
        raise MissingKeyError(
            "EIA_API_KEY is not set. Copy .env.example to .env in the repo root and paste "
            "your free key from https://www.eia.gov/opendata/register.php after EIA_API_KEY="
        )
    return key


def has_eia_api_key() -> bool:
    load_env()
    return bool(os.getenv("EIA_API_KEY", "").strip())


@lru_cache(maxsize=1)
def assumptions() -> dict[str, Any]:
    with open(CONFIG_DIR / "assumptions.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)
