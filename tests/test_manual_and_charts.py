import pandas as pd
import pytest

from gridkeepup import charts, config, manual


def test_manual_inputs_have_sources_and_positive_values():
    queue = manual.large_load_queue()
    assert (queue["total_large_load_gw"] > 0).all()
    assert queue["url"].str.startswith("http").all()
    assert queue["as_of"].is_monotonic_increasing
    stages = manual.large_load_stages()
    assert (stages["gw"] > 0).all()
    assert manual.reference("record_peak_demand") > 50_000


def test_v0_chart_title_reports_ratio_to_peak():
    queue = pd.DataFrame({
        "as_of": pd.to_datetime(["2025-01-01", "2026-01-01"]),
        "total_large_load_gw": [100.0, 400.0],
    })
    fig = charts.v0_queue_vs_peak(queue, record_peak_mw=80_000, demand=pd.DataFrame())
    assert "5.0x" in fig.layout.title.text
    assert len(fig.data) == 1  # no EIA demand yet -> queue trace only


def test_annual_peaks_uses_texas_time_and_skips_stub_years():
    # A full UTC year 2024: its first 6 hours fall on 31 Dec 2023 in Texas (a stub year).
    ts = pd.date_range("2024-01-01", "2024-12-31 23:00", freq="h", tz="UTC")
    values = pd.Series(50_000.0, index=range(len(ts)))
    values.iloc[0] = 99_000          # 2023 in Texas time: must not appear
    values.iloc[5500] = 85_000       # mid-August peak
    demand = pd.DataFrame({"timestamp_utc": ts, "value_mwh": values.to_numpy()})
    peaks = charts.annual_peaks(demand)
    assert peaks["year"].tolist() == [2024]
    assert peaks["peak_gw"].tolist() == [85.0]


def test_missing_eia_key_message(monkeypatch):
    monkeypatch.setattr(config, "load_env", lambda: None)
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    with pytest.raises(config.MissingKeyError, match=".env"):
        config.get_eia_api_key()
