"""Config values computed from data must match the data (skipped without the raw files)."""

import pytest

from gridkeepup import derive, lbnl
from gridkeepup.fetch import eia860m


@pytest.mark.skipif(eia860m.latest_file() is None or lbnl.latest_file() is None,
                    reason="raw EIA-860M / LBNL files not downloaded")
def test_config_matches_data():
    bad = derive.mismatches(derive.derive_all())
    assert not bad, "Run `uv run gridkeepup derive` and update the config:\n" + "\n".join(bad)


def test_mismatch_detects_drift():
    d = derive.Derived("supply.planned_storage_hours", 9.9, "x", "y", "z")
    assert derive.mismatches([d])
