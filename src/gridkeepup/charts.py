"""Charts shared by the CLI (HTML export) and the Streamlit app."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from gridkeepup import manual
from gridkeepup.fetch import eia930

QUEUE_COLOR = "#2563eb"
PEAK_COLOR = "#6b7280"


MIN_HOURS_FOR_PEAK = 8700   # skip years with only a few hours of data (e.g. UTC/Texas edges)


def annual_peaks(demand: pd.DataFrame) -> pd.DataFrame:
    """Highest hourly demand per calendar year (Texas time), in GW, for near-complete years."""
    if demand.empty:
        return pd.DataFrame(columns=["year", "peak_gw", "peak_hour"])
    local = demand.assign(ts=demand["timestamp_utc"].dt.tz_convert("US/Central"))
    years = local["ts"].dt.year
    counts = years.value_counts()
    local = local[years.map(counts) >= MIN_HOURS_FOR_PEAK]
    if local.empty:
        return pd.DataFrame(columns=["year", "peak_gw", "peak_hour"])
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
        annotation_position="top left",
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


def v1_demand_scenarios(proj: pd.DataFrame | None = None,
                        record_peak_mw: float | None = None) -> go.Figure:
    """New data center load at system peak, 2026 to horizon end: mid line, low-high band."""
    from gridkeepup import demand

    proj = demand.project() if proj is None else proj
    record_peak_mw = manual.reference("record_peak_demand") if record_peak_mw is None \
        else record_peak_mw
    wide = proj.pivot(index="year", columns="scenario", values="peak_gw")
    end = wide.index.max()
    lo, mid, hi = wide.loc[end, "low"], wide.loc[end, "mid"], wide.loc[end, "high"]
    share = mid / (record_peak_mw / 1000)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=list(wide.index) + list(wide.index[::-1]),
        y=list(wide["high"]) + list(wide["low"][::-1]),
        mode="lines", fill="toself", fillcolor="rgba(37, 99, 235, 0.15)", line={"width": 0},
        name="Low to high scenario", hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=wide.index, y=wide["mid"], mode="lines+markers", name="Mid scenario",
        line={"color": QUEUE_COLOR, "width": 3}, marker={"size": 8},
        customdata=wide[["low", "high"]].to_numpy(),
        hovertemplate="%{x}: %{y:.1f} GW (range %{customdata[0]:.1f} to "
                      "%{customdata[1]:.1f})<extra></extra>",
    ))
    for label, value in (("high", hi), ("low", lo)):
        fig.add_annotation(x=end, y=value, text=f"{label}: {value:.0f} GW", showarrow=False,
                           xanchor="left", xshift=10, font={"color": PEAK_COLOR})
    fig.add_annotation(x=end, y=mid, text=f"mid: {mid:.0f} GW", showarrow=False,
                       xanchor="left", xshift=10, font={"color": QUEUE_COLOR})
    fig.update_layout(
        title={
            "text": f"Data centers could add {lo:.0f} to {hi:.0f} GW to ERCOT's peak by {end}"
                    f"<br><sup>Mid case {mid:.0f} GW, about {share:.0%} of today's record "
                    "peak. New load only; excludes crypto and load already drawing power</sup>",
            "x": 0.01,
        },
        yaxis_title="GW added at system peak", xaxis={"dtick": 1, "title": None},
        template="simple_white", legend={"orientation": "h", "y": -0.15},
        margin={"t": 90, "r": 90},
    )
    fig.update_yaxes(rangemode="tozero", gridcolor="#e5e7eb", showgrid=True)
    return fig


FUEL_COLORS = {
    "Nuclear": "#7c3aed", "Coal": "#57534e", "Gas": "#f97316", "Wind": "#0ea5e9",
    "Solar": "#eab308", "Storage": "#10b981", "Hydro": "#1d4ed8", "Other": "#a8a29e",
}


def v2_supply_by_fuel(proj: pd.DataFrame | None = None) -> go.Figure:
    """Mid-scenario installed capacity by fuel (stacked), with low/high totals as markers."""
    from gridkeepup import supply

    proj = supply.project() if proj is None else proj
    mid = proj[proj["scenario"] == "mid"].pivot(index="year", columns="fuel",
                                                values="capacity_gw")
    tot = supply.totals(proj)
    last = tot.index.max()
    today = pd.Series(proj.attrs.get("today_by_fuel_gw") or mid.loc[tot.index.min()].to_dict())
    today_total = today.sum()
    by_fuel_growth = (mid.loc[last] - today.reindex(mid.columns, fill_value=0.0)) \
        .sort_values(ascending=False)
    top = ", ".join(f"{f.lower()} +{v:.0f}" for f, v in by_fuel_growth.head(3).items() if v >= 1)

    fig = go.Figure()
    for fuel in [f for f in supply.FUEL_ORDER if f in mid.columns]:
        fig.add_trace(go.Bar(x=mid.index, y=mid[fuel], name=fuel,
                             marker_color=FUEL_COLORS.get(fuel),
                             hovertemplate=f"{fuel} %{{x}}: %{{y:.1f}} GW<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=tot.index, y=tot["high"], mode="markers", name="High scenario total",
        marker={"symbol": "triangle-up", "size": 10, "color": PEAK_COLOR},
        hovertemplate="High total %{x}: %{y:.0f} GW<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=tot.index, y=tot["low"], mode="markers", name="Low scenario total",
        marker={"symbol": "triangle-down", "size": 10, "color": PEAK_COLOR},
        hovertemplate="Low total %{x}: %{y:.0f} GW<extra></extra>"))
    fig.update_layout(
        barmode="stack",
        title={"text": f"ERCOT capacity could grow from {today_total:.0f} GW today to "
                       f"{tot.loc[last, 'mid']:.0f} GW by {last} (mid case)"
                       f"<br><sup>Net summer GW, expected values from EIA-860M planned projects. "
                       f"Biggest gains since today: {top} GW</sup>", "x": 0.01},
        yaxis_title="Installed capacity (GW, net summer)", xaxis={"dtick": 1, "title": None},
        template="simple_white", legend={"orientation": "h", "y": -0.15}, margin={"t": 90},
    )
    fig.update_yaxes(gridcolor="#e5e7eb", showgrid=True)
    return fig
