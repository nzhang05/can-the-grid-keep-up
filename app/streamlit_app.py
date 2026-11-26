"""Can the grid keep up? Dashboard. Run: `uv run streamlit run app/streamlit_app.py`."""

import streamlit as st

from gridkeepup import charts, demand, manual

st.set_page_config(page_title="Can the grid keep up?", layout="wide")

st.title("Can the grid keep up?")
st.markdown(
    "How much power will Texas's planned data centers need, where will it come from, "
    "and can the ERCOT grid serve them in every hour? An open, reproducible model. "
    "**v1: demand.** Supply and hourly adequacy arrive in v2 and v3."
)

st.header("1. The queue")
st.plotly_chart(charts.v0_queue_vs_peak(), width="stretch")
st.caption(
    "A queue request is not a data center: most requests are early-stage and many will "
    "never connect."
)

st.header("2. How much is likely to connect")
st.plotly_chart(charts.v1_demand_scenarios(), width="stretch")
a = demand.DemandAssumptions.from_config()
st.caption(
    f"Each ERCOT queue stage x a connection probability x the data center share "
    f"({a.datacenter_share:.0%}), connecting from {a.first_new_connection_year} and ramping "
    f"over {a.ramp_years:.0f} years; {a.peak_factor:.0%} of nameplate drawn at peak. "
    "Assumptions and sources: docs/demand-assumptions.md."
)
with st.expander("Scenario table"):
    st.dataframe(demand.project(a), hide_index=True, width="stretch")

with st.expander("Sources for the numbers above"):
    queue = manual.large_load_queue()
    st.dataframe(
        queue[["as_of_month", "total_large_load_gw", "datacenter_share_pct", "source", "url",
               "verified"]],
        hide_index=True, width="stretch",
        column_config={"url": st.column_config.LinkColumn("link")},
    )
    n = manual.unverified_count()
    if n:
        st.warning(f"{n} hand-entered figures are not yet checked against the original slide.")
