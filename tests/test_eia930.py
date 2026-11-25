import pandas as pd
import pytest
import requests

from gridkeepup.fetch import eia930


def _row(period, value, **extra):
    return {"period": period, "respondent": "ERCO", "value": value,
            "value-units": "megawatthours", **extra}


def test_parse_rows_makes_utc_timestamps_and_numbers():
    df = eia930.parse_rows([_row("2024-08-20T22", "85000"), _row("2024-08-20T23", None)])
    assert str(df["timestamp_utc"].dt.tz) == "UTC"
    assert df["timestamp_utc"].iloc[0] == pd.Timestamp("2024-08-20 22:00", tz="UTC")
    assert df["value_mwh"].iloc[0] == 85000
    assert pd.isna(df["value_mwh"].iloc[1])
    assert "value_units" in df.columns  # hyphens become underscores


def test_parse_rows_empty():
    assert list(eia930.parse_rows([]).columns) == ["timestamp_utc", "value_mwh"]


class FakeResponse:
    def __init__(self, payload):
        self.payload, self.status_code, self.ok = payload, 200, True

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class FakeSession:
    """Serves 12 rows in pages of 5, like the EIA API does with `length`/`offset`."""

    def __init__(self):
        self.rows = [_row(f"2024-01-01T{h:02d}", 40000 + h) for h in range(12)]
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append(params)
        start = params["offset"]
        page = self.rows[start:start + 5]
        return FakeResponse({"response": {"total": str(len(self.rows)), "data": page}})


def test_fetch_route_paginates(monkeypatch):
    monkeypatch.setattr(eia930, "PAGE_SIZE", 5)
    session = FakeSession()
    df = eia930.fetch_route(eia930.DEMAND_ROUTE, {"respondent": ["ERCO"], "type": ["D"]},
                            "2024-01-01T00", "2024-01-01T11", "KEY", session)
    assert len(df) == 12
    assert [c["offset"] for c in session.calls] == [0, 5, 10]
    assert session.calls[0]["facets[respondent][]"] == ["ERCO"]
    assert session.calls[0]["frequency"] == "hourly"


def test_month_windows_cover_leap_february():
    windows = eia930.month_windows(2024)
    assert len(windows) == 12
    assert windows[0] == ("2024-01-01T00", "2024-01-31T23")
    assert windows[1] == ("2024-02-01T00", "2024-02-29T23")
    assert windows[-1] == ("2024-12-01T00", "2024-12-31T23")


class FlakySession:
    """Times out `failures` times, then answers."""

    def __init__(self, failures):
        self.failures, self.calls = failures, 0

    def get(self, url, params, timeout):
        self.calls += 1
        if self.calls <= self.failures:
            raise requests.Timeout("read timed out")
        return FakeResponse({"response": {"total": "0", "data": []}})


def test_get_json_retries_after_timeouts():
    session = FlakySession(failures=2)
    eia930._get_json(session, "u", {}, retries=3, sleep=lambda s: None)
    assert session.calls == 3


def test_get_json_gives_up_without_leaking_the_key():
    session = FlakySession(failures=5)
    params = {"api_key": "SECRET123", "start": "2024-08-01T00", "end": "2024-08-31T23"}
    with pytest.raises(eia930.EIAError) as err:
        eia930._get_json(session, "https://api.eia.gov/v2/x?api_key=SECRET123", params,
                         retries=3, sleep=lambda s: None)
    assert "SECRET123" not in str(err.value)
    assert "2024-08-01T00" in str(err.value)
    assert err.value.__cause__ is None and err.value.__suppress_context__


class StatusSession:
    def __init__(self, status):
        self.status = status

    def get(self, url, params, timeout):
        resp = FakeResponse({})
        resp.status_code, resp.ok = self.status, self.status < 400
        return resp


def test_non_retryable_http_error_is_redacted():
    with pytest.raises(eia930.EIAError, match="HTTP 403") as err:
        eia930._get_json(StatusSession(403), "u?api_key=SECRET123", {"api_key": "SECRET123"},
                         sleep=lambda s: None)
    assert "SECRET123" not in str(err.value)


def test_download_skips_failing_year_and_continues(tmp_path, monkeypatch):
    def fake_year(year, api_key, respondent, session):
        if year == 2024:
            raise eia930.EIAError("still failing")
        return eia930.parse_rows([_row(f"{year}-01-01T00", "1")])

    monkeypatch.setattr(eia930, "fetch_demand_year", fake_year)
    monkeypatch.setattr(eia930, "fetch_fuel_mix_year", fake_year)
    failed = eia930.download(2023, 2025, "KEY", out_dir=tmp_path)
    assert failed == ["demand_ERCO_2024.csv", "fuel_mix_ERCO_2024.csv"]
    assert (tmp_path / "demand_ERCO_2025.csv").exists()
    assert not (tmp_path / "demand_ERCO_2024.csv").exists()
