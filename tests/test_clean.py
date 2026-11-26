import numpy as np
import pandas as pd

from gridkeepup import clean


def _demand(hours, values):
    ts = pd.to_datetime(hours, utc=True)
    return pd.DataFrame({"timestamp_utc": ts, "value_mwh": values})


def test_missing_dst_hour_is_inserted_and_interpolated():
    # The real 2021 gap: 05:00 then 07:00 UTC on 7 Nov.
    raw = _demand(["2021-11-07 04:00", "2021-11-07 05:00", "2021-11-07 07:00",
                   "2021-11-07 08:00"], [40000, 41000, 43000, 44000])
    out = clean.clean_demand(raw)
    assert len(out) == 4 + 1
    row = out.loc[out["timestamp_utc"] == pd.Timestamp("2021-11-07 06:00", tz="UTC")].iloc[0]
    assert row["demand_mw"] == 42000
    assert row["was_filled"]


def test_zero_and_spike_are_replaced_and_flagged():
    vals = [50000, 51000, 0, 52000, 53000, 160000, 54000, 55000]
    hours = pd.date_range("2024-07-01", periods=len(vals), freq="h")
    out = clean.clean_demand(_demand(hours, vals))
    assert out["was_outlier"].sum() == 2
    assert out["demand_mw"].between(50000, 55000).all()


def test_long_gaps_stay_missing():
    hours = list(pd.date_range("2024-01-01", periods=3, freq="h")) + \
        list(pd.date_range("2024-01-01 12:00", periods=3, freq="h"))
    out = clean.clean_demand(_demand(hours, [1e4] * 6))
    assert out["demand_mw"].isna().sum() == 9   # 9-hour gap > MAX_FILL_HOURS


def test_uri_hours_are_flagged():
    hours = pd.date_range("2021-02-14", "2021-02-20", freq="h")
    out = clean.clean_demand(_demand(hours, np.full(len(hours), 6e4)))
    assert (out["event"] == "winter_storm_uri_load_shed").sum() == 96


def test_generation_pivots_and_fills():
    hours = pd.to_datetime(["2024-06-01 17:00", "2024-06-01 19:00"], utc=True)
    raw = pd.DataFrame({
        "timestamp_utc": list(hours) * 2,
        "fueltype": ["SUN", "SUN", "WND", "WND"],
        "value_mwh": [20000, 10000, 5000, 7000],
    })
    out = clean.clean_generation(raw)
    assert list(out.columns) == ["timestamp_utc", "SUN", "WND", "was_filled"]
    assert out.loc[1, "SUN"] == 15000 and out.loc[1, "was_filled"]


def test_quality_report_groups_by_texas_year():
    # 20:00 to 07:00 UTC; 06:00 UTC is midnight in Texas (CST = UTC-6).
    hours = pd.date_range("2023-12-31 20:00", periods=12, freq="h", tz="UTC")
    out = clean.clean_demand(_demand(hours, [5e4] * 12))
    report = clean.quality_report(out)
    assert report.index.tolist() == [2023, 2024]
    assert report["hours"].tolist() == [10, 2]
    assert not report["complete"].any()


def test_late_starting_fuel_is_zero_before_first_report_not_a_gap():
    """Battery storage only appears in EIA-930 from 2024: earlier hours are 0, not gaps."""
    hours = pd.date_range("2023-12-31 22:00", periods=4, freq="h", tz="UTC")
    raw = pd.DataFrame({
        "timestamp_utc": list(hours) + list(hours[2:]),
        "fueltype": ["NG"] * 4 + ["BAT", "BAT"],
        "value_mwh": [30000, 31000, 32000, 33000, -500, 800],
    })
    out = clean.clean_generation(raw)
    assert out["BAT"].tolist() == [0.0, 0.0, -500.0, 800.0]   # charging stays negative
    assert not out["was_filled"].any()
