"""Config values computed from data must match the data (skipped without the raw files)."""

import pandas as pd
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


@pytest.mark.skipif(lbnl.latest_file() is None, reason="raw LBNL file not downloaded")
def test_completion_curves_csv_matches_data():
    assert derive.curves_mismatch() is None


def test_completion_curves_csv_is_committed_and_cumulative():
    c = pd.read_csv(derive.CURVES_PATH)
    assert {"basis", "fuel", "k", "share", "sample_gw"} <= set(c.columns)
    assert {("signed", "All"), ("queue", "All")} <= set(zip(c["basis"], c["fuel"], strict=True))
    for _, grp in c.groupby(["basis", "fuel"]):
        s = grp.sort_values("k")["share"]
        assert (s.diff().dropna() >= -1e-12).all() and s.between(0, 1).all()
