# Can the grid keep up?

**How much power will Texas's planned data centers need, where will it come from, and can
the ERCOT grid serve them in every hour?** An open, reproducible model, built in public.

ERCOT is tracking several hundred gigawatts of large-load connection requests, mostly data
centers, against an all-time peak demand of about 85 GW. Most of those requests will never
connect. This project estimates how much will, what generation gets built to serve it, and
whether supply covers demand hour by hour, in normal and extreme weather.

## Status

| Version | Scope | Status |
| --- | --- | --- |
| v0 | Data foundations: fetchers, cleaning, manual inputs, first chart | done |
| v1 | Demand: low / mid / high data center GW by year to 2030 | first version |
| v2 | Supply: what gets built, by fuel | planned |
| v3 | Hourly adequacy: shortfall hours in every weather year | planned |
| v4 | Flexibility analysis and dashboard launch | planned |

## Quick start

Requires [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/nzhang05/can-the-grid-keep-up.git
cd can-the-grid-keep-up
uv sync
cp .env.example .env          # then paste your free EIA API key after EIA_API_KEY=
uv run gridkeepup check       # what's configured, what's on disk
uv run gridkeepup fetch all   # EIA-930 hourly data + EIA-860M generator inventory
uv run gridkeepup build       # load everything into data/grid.duckdb
uv run gridkeepup quality     # data quality report
uv run gridkeepup demand      # v1 demand scenarios
uv run gridkeepup chart v1    # writes outputs/v1_demand_scenarios.html
uv run streamlit run app/streamlit_app.py
```

Get an EIA API key (free, instant) at <https://www.eia.gov/opendata/register.php>.
Your `.env` file is git-ignored, so the key never leaves your machine.

## Data

| Source | Used for |
| --- | --- |
| [EIA-930 Hourly Electric Grid Monitor](https://www.eia.gov/electricity/gridmonitor/) | ERCOT hourly demand and generation by fuel, 2019 onwards |
| [EIA-860M](https://www.eia.gov/electricity/data/eia860m/) | Operating, planned and retiring generators in ERCOT |
| ERCOT large-load reports | The large-load queue by study stage (hand-entered, see [`data/manual`](data/manual)) |
| [Epoch AI data centers](https://epoch.ai/data/data-centers) | Site-level data center power (v1) |
| [LBNL Queued Up](https://emp.lbl.gov/queues) | How many queued projects actually get built (v2) |

Every modelling assumption lives in [`config/assumptions.yaml`](config/assumptions.yaml) with its source.

## Limits

This is a system-level adequacy model. It does not model transmission or local grid
constraints (network models are not public), prices, or water use.

## Layout

```
config/assumptions.yaml   every modelling assumption, with sources
data/manual/              hand-entered figures with source URLs (committed)
data/raw/                 downloaded files (git-ignored, rebuilt by `fetch`)
src/gridkeepup/           fetchers, storage, models, charts, CLI
app/streamlit_app.py      dashboard
tests/                    unit tests (no network needed)
```
