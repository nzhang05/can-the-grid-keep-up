import pandas as pd

from gridkeepup import config, epoch


def _fixture():
    sites = pd.DataFrame({
        "Name": ["A", "B", "C"],
        "Address": ["1 Rd, Abilene, TX 79601", "2 Rd, Claude, TX 79019", "3 Rd, Reno, NV"],
    })
    tl = pd.DataFrame({
        "Data center": ["A", "A", "A", "B", "C"],
        "Date": pd.to_datetime(["2026-01-01", "2027-06-01", "2028-06-01", "2027-01-01",
                                "2027-01-01"]),
        "Power (MW)": [200, 800, 1200, 500, 999],
    })
    return sites, tl


def test_texas_filter_and_asof_uses_latest_value():
    sites, tl = _fixture()
    assert set(epoch.texas_sites(sites)["Name"]) == {"A", "B"}
    assert epoch.facility_gw_asof(tl, {"A"}, pd.Timestamp("2027-12-31")) == 0.8


def test_compare_counts_growth_since_pause_and_excludes_flagged_sites():
    sites, tl = _fixture()
    cfg = dict(config.assumptions())
    cfg["crosscheck"] = {"epoch_since": "2026-08-01", "epoch_possibly_not_ercot": ["B"]}
    proj = pd.DataFrame({"scenario": ["low", "mid", "high"] * 2, "year": [2027] * 3 + [2028] * 3,
                         "ramped_gw": [0.1, 0.3, 0.5, 0.5, 1.0, 2.0]})
    out = epoch.compare(sites, tl, proj, cfg).set_index("year")
    assert out.loc[2027, "epoch_tx_all_gw"] == 1.1           # A +0.6, B +0.5
    assert out.loc[2027, "epoch_tx_likely_ercot_gw"] == 0.6  # B flagged, not counted
    assert out.loc[2028, "epoch_tx_likely_ercot_gw"] == 1.0
    assert not out.loc[2027, "model_high_covers_epoch"]
    assert out.loc[2028, "model_high_covers_epoch"]
