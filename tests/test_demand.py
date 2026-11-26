import copy

import pytest

from gridkeepup import config, demand


def _cfg(**demand_overrides):
    cfg = copy.deepcopy(config.assumptions())
    cfg["demand"].update(demand_overrides)
    return cfg


def _simple(**kw):
    """One 10 GW stage, 50% in mid, connecting in a single year."""
    stage = {"name": "S", "gw": 10.0, "in_baseline": False,
             "p_connect": {"low": 0.2, "mid": 0.5, "high": 1.0}, "connect_years": [2027]}
    cfg = _cfg(stages=[stage], datacenter_share=1.0, include_crypto=False, ramp_years=2,
               load_factor=0.5, peak_factor=1.0, **kw)
    return demand.DemandAssumptions.from_config(cfg)


def test_ramp_fraction_mid_year_convention():
    assert demand.ramp_fraction(-1, 3) == 0.0
    assert demand.ramp_fraction(0, 3) == pytest.approx(0.5 / 3)
    assert demand.ramp_fraction(1, 3) == pytest.approx(1.5 / 3)
    assert demand.ramp_fraction(5, 3) == 1.0


def test_single_cohort_ramps_then_plateaus():
    out = demand.project(_simple()).query("scenario == 'mid'").set_index("year")
    assert out.loc[2026, "connected_gw"] == 0
    assert out.loc[2027, "connected_gw"] == 5.0
    assert out.loc[2027, "ramped_gw"] == pytest.approx(5.0 * 0.25)
    assert out.loc[2028, "ramped_gw"] == pytest.approx(5.0 * 0.75)
    assert out.loc[2029, "ramped_gw"] == 5.0
    assert out.loc[2029, "avg_gw"] == 2.5
    assert out.loc[2029, "energy_twh"] == pytest.approx(2.5 * 8760 / 1000)


def test_baseline_stage_is_not_counted_again():
    a = demand.DemandAssumptions.from_config()
    baseline = [s for s in a.stages if s.in_baseline]
    assert baseline, "config should mark already-energized load as in_baseline"
    assert not set(demand.cohorts(a, "high")["stage"]) & {s.name for s in baseline}


def test_crypto_switch_scales_by_datacenter_share():
    a = demand.DemandAssumptions.from_config(_cfg(include_crypto=False))
    b = demand.DemandAssumptions.from_config(_cfg(include_crypto=True))
    dc = demand.project(a).query("scenario=='mid' and year==2030")["connected_gw"].item()
    all_ = demand.project(b).query("scenario=='mid' and year==2030")["connected_gw"].item()
    assert dc == pytest.approx(all_ * a.datacenter_share, rel=1e-3)


def test_scenarios_are_ordered_every_year():
    out = demand.project().pivot(index="year", columns="scenario", values="peak_gw")
    assert ((out["low"] <= out["mid"]) & (out["mid"] <= out["high"])).all()


def test_by_stage_sums_to_connected_total():
    a = demand.DemandAssumptions.from_config()
    totals = demand.by_stage(a).sum()
    proj = demand.project(a).query(f"year == {a.end_year}").set_index("scenario")
    for s in demand.SCENARIOS:
        assert totals[s] == pytest.approx(proj.loc[s, "connected_gw"], abs=0.02)


def test_stage_ramp_override():
    stage = {"name": "Ramping", "gw": 2.0, "in_baseline": False, "ramp_years": 2,
             "p_connect": {"low": 1.0, "mid": 1.0, "high": 1.0}, "connect_years": [2026]}
    cfg = _cfg(stages=[stage], datacenter_share=1.0, include_crypto=False, ramp_years=3)
    out = demand.project(demand.DemandAssumptions.from_config(cfg))
    mid = out.query("scenario == 'mid'").set_index("year")["ramped_gw"]
    assert mid[2026] == pytest.approx(2.0 * 0.25)   # (0 + 0.5) / 2, not / 3
    assert mid[2027] == pytest.approx(2.0 * 0.75)
    assert mid[2028] == 2.0
