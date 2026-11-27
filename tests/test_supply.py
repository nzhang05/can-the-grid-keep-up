import copy

import pandas as pd
import pytest

from gridkeepup import config, supply


def _inventory():
    op = pd.DataFrame({
        "technology": ["Natural Gas Fired Combined Cycle", "Conventional Steam Coal", "Batteries",
                       "Petroleum Liquids"],
        "net_summer_capacity_mw": [1000.0, 500.0, 100.0, 10.0],
        "planned_retirement_year": [" ", 2028, " ", " "],
        "nameplate_energy_capacity_mwh": [None, None, 200.0, None],
    })
    pl = pd.DataFrame({
        "technology": ["Solar Photovoltaic", "Batteries", "Natural Gas Fired Combined Cycle"],
        "status": ["(U) Under construction, less than or equal to 50 percent complete",
                   "(TS) Construction complete, but not yet in commercial operation",
                   "(P) Planned for installation, but regulatory approvals not initiated"],
        "planned_operation_year": [2027, 2026, 2028],
        "net_summer_capacity_mw": [400.0, 50.0, 800.0],
    })
    return {"operating": op, "planned": pl}


def _assumptions(**overrides):
    cfg = copy.deepcopy(config.assumptions())
    cfg["supply"].update(overrides)
    return supply.SupplyAssumptions.from_config(cfg)


def test_status_code_and_fuel_groups():
    assert supply.status_code("(TS) Construction complete") == "TS"
    assert supply.fuel_group("Onshore Wind Turbine") == "Wind"
    assert supply.fuel_group("Petroleum Liquids") == supply.OTHER


def test_project_applies_probability_delay_and_retirement():
    a = _assumptions()
    out = supply.project(_inventory(), a, gis=pd.DataFrame())
    mid = out[out["scenario"] == "mid"].pivot(index="year", columns="fuel", values="capacity_gw")
    p_u, p_p = a.probability["U"]["mid"], a.probability["P"]["mid"]
    d_p = a.delay_years["P"]["mid"]
    assert mid.loc[2026, "Solar"] == 0                       # planned 2027, U has no mid delay
    assert mid.loc[2027, "Solar"] == pytest.approx(0.4 * p_u, abs=1e-3)
    assert mid.loc[2027, "Coal"] == 0.5 and mid.loc[2028, "Coal"] == 0   # retires in 2028
    assert mid.loc[2028 + d_p - 1, "Gas"] == 1.0              # P unit not yet arrived
    assert mid.loc[2028 + d_p, "Gas"] == pytest.approx(1.0 + 0.8 * p_p, abs=1e-3)
    assert mid.loc[2026, "Other"] == 0.01


def test_storage_energy_uses_fleet_mwh_and_planned_hours():
    a = _assumptions(planned_storage_hours=2.0)
    out = supply.project(_inventory(), a, gis=pd.DataFrame())
    st = out[(out["scenario"] == "high") & (out["fuel"] == "Storage")].set_index("year")
    assert st.loc[2026, "storage_gwh"] == pytest.approx(0.2 + 0.05 * 2.0, abs=1e-3)
    assert out.attrs["operating_storage_hours"] == 2.0


def test_unknown_status_code_is_an_error():
    inv = _inventory()
    inv["planned"].loc[0, "status"] = "(XX) Something new"
    with pytest.raises(ValueError, match="XX"):
        supply.project(inv, _assumptions(), gis=pd.DataFrame())


def test_scenarios_ordered_and_low_never_above_high():
    out = supply.project(_inventory(), _assumptions(), gis=pd.DataFrame())
    t = supply.totals(out)
    assert (t["low"] <= t["mid"]).all() and (t["mid"] <= t["high"]).all()


def test_config_probabilities_are_monotonic_by_stage():
    """Later stages must never be less likely than earlier ones."""
    p = config.assumptions()["supply"]["status_probability"]
    order = ["P", "L", "T", "U", "V", "TS"]
    for scenario in ("low", "mid", "high"):
        vals = [p[s][scenario] for s in order]
        assert vals == sorted(vals), scenario
