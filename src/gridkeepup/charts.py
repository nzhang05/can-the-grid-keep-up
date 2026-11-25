"""Charts shared by the CLI (HTML export) and the Streamlit app."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from gridkeepup import manual
from gridkeepup.fetch import eia930

QUEUE_COLOR = "#2563eb"
PEAK_COLOR = "#6b7280"


def annual_peaks(demand: pd.DataFrame) -> pd.DataFrame:
    """Highest hourly demand per calendar year (Texas time), in GW."""
    if demand.empty:
        return pd.DataFrame(columns=["year", "peak_gw", "peak_hour"])
    local = demand.assign(ts=demand["timestamp_utc"].dt.tz_convert("US/Central"))
    idx = local.groupby(local["ts"].dt.year)["value_mwh"].idxmax().dropna()
    peaks = local.loc[idx, ["ts", "value_mwh"]]
    return pd.DataFrame({
        "year": peaks["ts"].dt.year.to_numpy(),
        "peak_gw": peaks["value_mwh"].to_numpy() / 1000,
        "peak_hour": peaks["ts"].to_numpy(),
    })


def v0_queue_vs_peak(queue: pd.DataFrame | None = None,
                     record_peak_mw: float | None = None,
                     demand: pd.DataFrame | None = None) -> go.Figure:
    """ERCOT's large-load queue over time against the grid's all-time peak demand."""
    queue = manual.large_load_queue() if queue is None else queue
    record_peak_mw = manual.reference("record_peak_demand") if record_peak_mw is None \
        else record_peak_mw
    demand = eia930.load("demand") if demand is None else demand
    peak_gw = record_peak_mw / 1000
    try:
        peak_label = f"{manual.reference_date('record_peak_demand'):%b %Y}"
    except (KeyError, IndexError, ValueError):
        peak_label = "record"
    latest = queue.iloc[-1]
    ratio = latest["total_large_load_gw"] / peak_gw

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=queue["as_of"], y=queue["total_large_load_gw"], mode="lines+markers",
        name="Large-load requests tracked by ERCOT",
        line={"color": QUEUE_COLOR, "width": 3}, marker={"size": 8},
        hovertemplate="%{x|%b %Y}: %{y:,.0f} GW<extra></extra>",
    ))
    peaks = annual_peaks(demand)
    if not peaks.empty:
        fig.add_trace(go.Scatter(
            x=pd.to_datetime(peaks["year"].astype(str) + "-07-01"), y=peaks["peak_gw"],
            mode="markers", name="Actual annual peak demand (EIA-930)",
            marker={"color": PEAK_COLOR, "size": 8, "symbol": "diamond"},
            hovertemplate="%{x|%Y} peak: %{y:,.1f} GW<extra></extra>",
        ))
    fig.add_hline(
        y=peak_gw, line={"color": PEAK_COLOR, "dash": "dash", "width": 1.5},
        annotation_text=f"All-time peak demand: {peak_gw:,.1f} GW ({peak_label})",
        annotation_position="bottom right",
    )
    fig.update_layout(
        title={
            "text": f"ERCOT's large-load queue is {ratio:.1f}x the grid's all-time peak"
                    f"<br><sup>{latest['total_large_load_gw']:,.0f} GW of requests "
                    f"({latest['as_of']:%b %Y}), mostly data centers</sup>",
            "x": 0.01,
        },
        yaxis_title="GW", xaxis_title=None, template="simple_white",
        legend={"orientation": "h", "y": -0.15}, margin={"t": 90},
        hovermode="x unified",
    )
    fig.update_yaxes(rangemode="tozero", gridcolor="#e5e7eb", showgrid=True)
    return fig
