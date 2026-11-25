"""Can the grid keep up? Dashboard. Run: `uv run streamlit run app/streamlit_app.py`."""

import streamlit as st

from gridkeepup import charts, manual

st.set_page_config(page_title="Can the grid keep up?", layout="wide")

st.title("Can the grid keep up?")
st.markdown(
    "How much power will Texas's planned data centers need, where will it come from, "
    "and can the ERCOT grid serve them in every hour? An open, reproducible model. "
    "**v0: data foundations.** Demand, supply and hourly adequacy arrive in v1 to v3."
)

st.plotly_chart(charts.v0_queue_vs_peak(), use_container_width=True)

st.caption(
    "A queue request is not a data center: most requests are early-stage and many will "
    "never connect. Sorting real demand from speculative demand is the job of v1."
)

with st.expander("Sources for the numbers above"):
    queue = manual.large_load_queue()
    st.dataframe(
        queue[["as_of_month", "total_large_load_gw", "datacenter_share_pct", "source", "url",
               "verified"]],
        hide_index=True, use_container_width=True,
        column_config={"url": st.column_config.LinkColumn("link")},
    )
    n = manual.unverified_count()
    if n:
        st.warning(f"{n} hand-entered figures are not yet checked against the original slide.")
