"""Every assumption in the config, and every tunable constant in the code, must be listed
in docs/assumptions.md. Add it to the register when you add it to the model."""

import re

from gridkeepup import clean, config
from gridkeepup.paths import ROOT

REGISTER = (ROOT / "docs" / "assumptions.md").read_text(encoding="utf-8")


def _keys(node, prefix=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _keys(v, f"{prefix}{k}.")
    elif isinstance(node, list):
        for item in node:
            yield from _keys(item, prefix)


def test_every_config_key_is_in_the_register():
    cfg = config.assumptions()
    skip = {"low", "mid", "high", "gw", "name"}   # generic field names inside stages
    missing = sorted({k for k in _keys(cfg) if k not in skip and f"`{k}" not in REGISTER
                      and k not in REGISTER})
    assert not missing, f"Add these config assumptions to docs/assumptions.md: {missing}"


def test_every_stage_is_in_the_register():
    names = [s["name"] for s in config.assumptions()["demand"]["stages"]]
    missing = [n for n in names if n not in REGISTER]
    assert not missing, f"Add these stages to docs/assumptions.md: {missing}"


def test_cleaning_constants_are_in_the_register():
    constants = [n for n in dir(clean) if re.fullmatch(r"[A-Z][A-Z_]+", n)]
    missing = [n for n in constants if n not in REGISTER]
    assert not missing, f"Add these cleaning constants to docs/assumptions.md: {missing}"
