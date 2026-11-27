import copy

import pandas as pd
import pytest

from gridkeepup import config, lbnl, supply
from gridkeepup.fetch import ercot_gis


def test_odds_rule_low_mid_high():
    shares = pd.DataFrame({"operational": [0.42], "active": [0.48], "withdrawn": [0.10]},
                          index=["Storage"])
    odds = lbnl.odds_from_shares(shares).loc["Storage"]
    assert (odds["low"], odds["mid"], odds["high"]) == (0.42, 0.66, 0.90)


def test_post_agreement_shares_capacity_weighted_and_cutoff():
    e = pd.DataFrame({
        "q_status": ["operational", "withdrawn", "active", "operational"],
        "mw": [300.0, 100.0, 100.0, 999.0],
        "ia_date": pd.to_datetime(["2015-01-01", "2016-01-01", "2020-01-01", "2024-01-01"]),
        "fuel": ["Solar"] * 4,
    })
    s = lbnl.post_agreement_shares(e).loc["Solar"]      # 2024 IA is after the 2022 cutoff
    assert s["operational"] == pytest.approx(0.6) and s["active"] == pytest.approx(0.2)
    assert s["gw"] == pytest.approx(0.5)


def test_gis_fuel_codes_and_stage():
    assert ercot_gis.fuel_group("OTH", "BA") == "Storage"
    assert ercot_gis.fuel_group("OTH", "OT") == "Other"
    assert ercot_gis.fuel_group("SOL", "PV") == "Solar"
    row = pd.Series({"Approved for Synchronization": pd.NaT, "Approved for Energization": pd.NaT,
                     "Construction Start": pd.NaT, "IA Signed": pd.Timestamp("2025-01-01")})
    assert ercot_gis.stage(row) == "signed"


def _inventory():
    op = pd.DataFrame({"technology": ["Natural Gas Fired Combined Cycle"],
                       "net_summer_capacity_mw": [1000.0], "planned_retirement_year": [" "],
                       "nameplate_energy_capacity_mwh": [None]})
    pl = pd.DataFrame({
        "technology": ["Solar Photovoltaic", "Solar Photovoltaic"],
        "status": ["(U) Under construction", "(P) Planned"],
        "planned_operation_year": [2027, 2029],          # the 2029 EIA unit is dropped
        "net_summer_capacity_mw": [100.0, 500.0],
    })
    return {"operating": op, "planned": pl}


def _gis(stage="construction"):
    return pd.DataFrame({
        "inr": ["a", "b", "c"], "project_name": ["A", "B", "C"], "county": ["X"] * 3,
        "fuel": ["Gas", "Nuclear", "Solar"], "stage": [stage] * 3,
        "cod_year": [2028, 2028, 2027],                  # the 2027 queue project is dropped
        "mw_nameplate": [1000.0, 100.0, 777.0],
        "ia_year": [2025, 2025, 2025], "queue_year": [2023, 2023, 2023],
    })


def _curves():
    k = list(range(13))
    share = [0.0, 0.1, 0.3, 0.5, 0.6] + [0.6] * 8           # plateau 0.6 from year 4
    rows = [{"basis": b, "fuel": f, "k": i, "share": s, "sample_gw": 10.0}
            for b in ("signed", "queue") for f in ("All", "Gas") for i, s in zip(k, share,
                                                                                  strict=True)]
    return pd.DataFrame(rows)


def _a(enabled=True):
    cfg = copy.deepcopy(config.assumptions())
    cfg["supply"]["ercot_gis"]["enabled"] = enabled
    return supply.SupplyAssumptions.from_config(cfg)


def test_pipeline_splits_sources_by_year_and_converts_to_summer():
    a = _a()
    pipe = supply.pipeline(_inventory(), _gis(), a, "mid")
    assert list(pipe["source"]) == ["EIA-860M", "ERCOT GIS", "ERCOT GIS"]
    gas = pipe[(pipe["source"] == "ERCOT GIS") & (pipe["fuel"] == "Gas")].iloc[0]
    assert gas["mw"] == pytest.approx(1000 * a.summer_ratio["Gas"])
    assert gas["p"] == a.gis_probability["construction"]["mid"]
    assert gas["arrives"] == 2028 + a.gis_delay_years["construction"]["mid"]


def test_online_by_rescales_shape_and_conditions_on_not_online_yet():
    curve = pd.Series([0.0, 0.1, 0.3, 0.5, 0.6], index=range(5))
    assert supply.online_by(curve, 0, 0, 0.3) == 0.0
    assert supply.online_by(curve, 0, 4, 0.3) == pytest.approx(0.3)     # plateau -> level
    assert supply.online_by(curve, 0, 2, 0.3) == pytest.approx(0.15)    # shape: 0.3/0.6 of it
    # two years in and not online: (G(4) - G(2)) / (1 - G(2)) with G = curve / 0.6 * 0.3
    assert supply.online_by(curve, 2, 9, 0.3) == pytest.approx((0.3 - 0.15) / 0.85)


def test_curve_timed_rows_respect_cod_and_sum_to_conditional_odds():
    a = _a()
    pipe = supply.pipeline(_inventory(), _gis("signed"), a, "mid", curves=_curves())
    q = pipe[pipe["source"] == "ERCOT GIS"]
    assert (q["arrives"] >= 2028).all() and (q["p"] > 0).all()
    gas = q[q["fuel"] == "Gas"]                     # signed 2025, age 1 at the 2026 snapshot
    level = a.gis_p("signed", "Gas", "mid")
    g = pd.Series([0.0, 0.1, 0.3, 0.5, 0.6]) / 0.6 * level
    assert gas["p"].sum() == pytest.approx((g[4] - g[1]) / (1 - g[1]))
    nuc = q[q["fuel"] == "Nuclear"]                 # no fuel-specific curve or odds -> All/Other
    assert nuc["p"].sum() > 0


def test_tax_credit_factor_only_hits_queue_wind_and_solar():
    a = _a()
    tc = a.tax_credit
    assert a.gis_p("signed", "Solar", "low") == pytest.approx(
        a.gis_probability["signed"]["Solar"]["low"] * tc["low"])
    assert a.gis_p("study", "Wind", "mid") == pytest.approx(
        a.gis_probability["study"]["Wind"]["mid"] * tc["mid"])
    assert a.gis_p("signed", "Storage", "low") == a.gis_probability["signed"]["Storage"]["low"]
    assert a.gis_p("construction", "Solar", "low") == a.gis_probability["construction"]["low"]


def test_disabled_queue_uses_all_eia_planned():
    pipe = supply.pipeline(_inventory(), _gis(), _a(enabled=False), "mid")
    assert set(pipe["source"]) == {"EIA-860M"} and len(pipe) == 2
