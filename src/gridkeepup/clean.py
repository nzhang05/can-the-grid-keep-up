"""Turn raw EIA-930 downloads into complete, checked hourly series.

* every UTC hour present exactly once (EIA occasionally drops an hour, e.g. the
  2021 daylight-saving fall-back)
* short gaps filled by linear interpolation and flagged, never silently
* implausible values (zero or negative demand, single-hour spikes) set aside and
  filled the same way
* known events where the data is not true demand (Winter Storm Uri load shed) flagged
"""

from __future__ import annotations

import pandas as pd

MAX_FILL_HOURS = 6        # longer gaps stay missing and are reported
STORAGE_FUELS = {"BAT", "UES"}   # EIA-930 storage categories: net output, negative when charging
SPIKE_RATIO = 1.5         # an hour > 1.5x both neighbours (or < 1/1.5) is a spike

# Periods where reported load is not underlying demand. Times are UTC.
KNOWN_EVENTS = {
    "winter_storm_uri_load_shed": ("2021-02-15 06:00", "2021-02-19 06:00"),
}


def complete_hours(df: pd.DataFrame, value_col: str = "value_mwh") -> pd.DataFrame:
    """One row per UTC hour from the first to the last timestamp; missing hours are NaN."""
    s = df.drop_duplicates("timestamp_utc").set_index("timestamp_utc")[value_col].sort_index()
    full = pd.date_range(s.index.min(), s.index.max(), freq="h", tz="UTC")
    return s.reindex(full).rename_axis("timestamp_utc").to_frame(value_col)


def _spikes(s: pd.Series) -> pd.Series:
    prev, nxt = s.shift(1), s.shift(-1)
    up = (s > SPIKE_RATIO * prev) & (s > SPIKE_RATIO * nxt)
    down = (s * SPIKE_RATIO < prev) & (s * SPIKE_RATIO < nxt)
    return (up | down).fillna(False)


def _short_gaps(missing: pd.Series, max_len: int = MAX_FILL_HOURS) -> pd.Series:
    """True for missing hours that belong to a run of at most ``max_len`` missing hours."""
    run_id = (missing != missing.shift()).cumsum()
    run_len = missing.groupby(run_id).transform("size")
    return missing & (run_len <= max_len)


def _fill(s: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Interpolate gaps of up to MAX_FILL_HOURS; longer gaps stay entirely missing."""
    missing = s.isna()
    fillable = _short_gaps(missing)
    interpolated = s.interpolate(limit_area="inside")
    filled = s.where(~fillable, interpolated)
    return filled, fillable & filled.notna()


def event_flags(index: pd.DatetimeIndex) -> pd.Series:
    flag = pd.Series("", index=index, dtype="object")
    for name, (start, end) in KNOWN_EVENTS.items():
        in_event = (index >= pd.Timestamp(start, tz="UTC")) & (index < pd.Timestamp(end, tz="UTC"))
        flag[in_event] = name
    return flag


def clean_demand(raw: pd.DataFrame) -> pd.DataFrame:
    """Columns: timestamp_utc, demand_mw, was_filled, was_outlier, event."""
    if raw.empty:
        return pd.DataFrame(columns=["timestamp_utc", "demand_mw", "was_filled",
                                     "was_outlier", "event"])
    df = complete_hours(raw)
    s = df["value_mwh"].astype(float)
    bad = (s <= 0) | _spikes(s)
    s = s.mask(bad)
    s, was_filled = _fill(s)
    out = pd.DataFrame({
        "demand_mw": s,
        "was_filled": was_filled,
        "was_outlier": bad,
        "event": event_flags(df.index),
    })
    return out.reset_index()


def clean_generation(raw: pd.DataFrame) -> pd.DataFrame:
    """Wide hourly MW by fuel (columns = EIA fuel codes: SUN, WND, NG, ...), gaps filled."""
    if raw.empty:
        return pd.DataFrame(columns=["timestamp_utc"])
    wide = (raw.drop_duplicates(["timestamp_utc", "fueltype"])
               .pivot(index="timestamp_utc", columns="fueltype", values="value_mwh")
               .sort_index())
    full = pd.date_range(wide.index.min(), wide.index.max(), freq="h", tz="UTC")
    wide = wide.reindex(full).rename_axis("timestamp_utc")
    # Categories EIA added later (battery storage from 2024) are empty before their first
    # report: that is "not reported", not a gap, so it neither counts as one nor gets filled.
    before_first = wide.apply(lambda col: col.index < col.first_valid_index())
    gaps = (wide.isna() & ~before_first).any(axis=1)
    # Storage is net generation and is negative while charging, so only non-storage
    # categories are clipped at zero.
    storage = [c for c in wide.columns if c in STORAGE_FUELS]
    wide = wide.apply(lambda col: _fill(col)[0])
    other = wide.columns.difference(storage)
    wide[other] = wide[other].clip(lower=0)
    wide = wide.mask(before_first, 0.0)
    wide.columns.name = None
    wide["was_filled"] = gaps & wide.notna().all(axis=1)
    return wide.reset_index()


def quality_report(demand: pd.DataFrame) -> pd.DataFrame:
    """Per Texas calendar year: hours, gaps filled, outliers, still missing, peak, energy.

    ``complete`` is False for years only partly covered (e.g. the first UTC hours of a
    download that still fall on 31 December in Texas); their peak and energy are partial.
    """
    if demand.empty:
        return pd.DataFrame()
    local = demand["timestamp_utc"].dt.tz_convert("US/Central")
    year = local.dt.year
    g = demand.groupby(year)
    expected = pd.Series({y: 8784 if pd.Timestamp(year=y, month=1, day=1).is_leap_year
                          else 8760 for y in g.groups})
    return pd.DataFrame({
        "complete": g.size() >= expected,
        "hours": g.size(),
        "filled": g["was_filled"].sum(),
        "outliers": g["was_outlier"].sum(),
        "still_missing": g["demand_mw"].apply(lambda s: int(s.isna().sum())),
        "event_hours": g["event"].apply(lambda s: int((s != "").sum())),
        "peak_gw": g["demand_mw"].max() / 1000,
        "energy_twh": g["demand_mw"].sum() / 1e6,
    }).rename_axis("year").round(2)
