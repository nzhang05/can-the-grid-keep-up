import copy
import math

import numpy as np
import pandas as pd
import pytest

from gridkeepup import adequacy as ad
from gridkeepup import config


def _a(**over):
    a = ad.AdequacyAssumptions.from_config()
    return ad.AdequacyAssumptions(**{**a.__dict__, **over})


def test_copt_matches_binomial():
    # 3 identical 100 MW units with 10% outage: available 0/100/200/300 MW is binomial
    c = ad.COPT.build(np.array([100.0] * 3), np.array([0.1] * 3), step=10)
    probs = {mw: p for mw, p in zip(c.mw, c.pmf, strict=True) if p > 0}
    for k in range(4):
        expected = math.comb(3, k) * 0.9 ** k * 0.1 ** (3 - k)
        assert probs[100 * k] == pytest.approx(expected)
    assert c.mean() == pytest.approx(270.0)


def test_copt_shortfall_probability_and_expected_unserved():
    c = ad.COPT.build(np.array([100.0, 100.0]), np.array([0.5, 0.5]), step=10)
    lolp, eue = c.shortfall(np.array([150.0, 200.0, 0.0]))
    # need 150: short if 0 or 100 available (p 0.25 + 0.5); E[short] = .25*150 + .5*50
    assert lolp[0] == pytest.approx(0.75) and eue[0] == pytest.approx(62.5)
    # need exactly 200: short unless both up (0.75)
    assert lolp[1] == pytest.approx(0.75) and eue[1] == pytest.approx(0.25 * 200 + 0.5 * 100)
    assert lolp[2] == 0 and eue[2] == 0


def test_storage_never_exceeds_power_or_energy_and_shaves_the_peak():
    need = np.array([90.0, 100.0, 130.0, 120.0, 90.0, 80.0])
    safe = np.full(6, 110.0)
    dis, chg = ad.dispatch_storage(need, safe, power=15.0, energy=20.0, round_trip=0.8)
    assert (dis <= 15 + 1e-9).all() and (chg <= 15 + 1e-9).all()
    assert dis.sum() <= 20 + 1e-6
    assert dis[2] > dis[3] > 0                     # the highest hour is shaved most
    assert dis[0] == dis[1] == 0                    # no discharge below the safe level
    assert ((dis > 0) & (chg > 0)).sum() == 0        # never both in one hour


def test_storage_recharges_only_with_safe_room():
    need = np.array([120.0, 50.0, 120.0])
    safe = np.full(3, 100.0)
    dis, chg = ad.dispatch_storage(need, safe, power=30.0, energy=20.0, round_trip=0.5)
    # it sees two risky hours ahead and does not count on recharging: splits 20 MWh 10 / 10
    assert dis[0] == pytest.approx(10.0)
    assert chg[1] == pytest.approx(20.0)            # refills the 10 MWh used (at 50%)
    assert dis[2] == pytest.approx(20.0)


def test_uri_rebuild_raises_load_to_ercot_estimate_and_never_lowers():
    idx = pd.date_range("2021-02-13 00:00", "2021-02-21 00:00", freq="h", tz="UTC")
    load = pd.Series(50_000.0, index=idx)
    load[(idx >= "2021-02-14 06:00") & (idx < "2021-02-15 06:00")] = np.linspace(55, 69, 24) * 1e3
    out = ad.rebuild_uri(load)
    shed = (idx >= "2021-02-15 06:00") & (idx < "2021-02-19 06:00")
    assert out[shed].max() == pytest.approx(76_819)
    assert (out >= load).all() and (out[~shed] == load[~shed]).all()


def test_rare_event_weighted_by_annual_probability():
    a = _a()
    p = a.rare["uri"]["annual_probability"]
    rows = pd.DataFrame({"lole": [0.1, 0.3], "lolh": [1.0, 1.0], "eue_gwh": [1.0, 3.0],
                         "winter_lole": [0.0, 0.2],
                         "rare_uri_lole": [5.0, 0.0], "rare_uri_lolh": [60.0, 0.0],
                         "rare_uri_eue_gwh": [400.0, 0.0]})
    e = ad.expected(rows, a)
    assert e["lole"] == pytest.approx(0.2 + p * 5.0)
    assert e["eue_gwh"] == pytest.approx(2.0 + p * 400.0)
    assert e["winter_lole"] == pytest.approx(0.1 + p * 5.0)


def test_chp_flag_excludes_non_chp():
    s = pd.Series(["IPP CHP", "IPP Non-CHP", "Industrial CHP", "Electric Utility"])
    assert list(ad.is_chp(s)) == [True, False, True, False]


def test_storm_extra_only_inside_windows_and_net_of_normal_outages():
    a = _a()
    idx = pd.DatetimeIndex(["2022-12-23 12:00", "2022-12-28 12:00"], tz="UTC")
    extra = ad.storm_extra_mw(idx, expected_outage_mw=6000.0, a=a)
    assert extra[0] == pytest.approx(a.storms["elliott"]["thermal_out_mw"] - 6000.0)
    assert extra[1] == 0


def test_config_growth_rates_ordered_and_standard_is_texas():
    a = ad.AdequacyAssumptions.from_config()
    g = a.load_growth
    assert g["low"] < g["mid"] < g["high"]
    assert a.standard == 0.1 and a.reserve_mw == 1500


def test_results_files_have_every_scenario_pair():
    s = ad.load_results("adequacy_summary")
    if s.empty:
        pytest.skip("run `gridkeepup adequacy` first")
    assert len(s.groupby(["demand", "supply"])) == 9
    assert (s["lole"] >= 0).all() and s["winter_share"].between(0, 1).all()
    cfg = copy.deepcopy(config.assumptions())
    assert s["year"].max() == cfg["horizon"]["end_year"]
