import pandas as pd

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
        self.payload, self.status_code = payload, 200

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
