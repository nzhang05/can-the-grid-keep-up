"""Command line entry point: `uv run gridkeepup <command>`.

  check                 what's configured and which inputs are on disk
  fetch eia930          hourly ERCOT demand and generation by fuel (needs EIA_API_KEY)
  fetch eia860m         latest EIA-860M generator inventory
  fetch all             both of the above
  build                 load every input into data/grid.duckdb
  quality               per-year data quality report for hourly demand
  demand                v1 data center demand scenarios (from config/assumptions.yaml)
  crosscheck            compare the demand model with Epoch AI's Texas data centers
  supply                v2 installed capacity by fuel and year
  derive                recompute every data-derived config value; write docs/derived-values.md
  chart v0|v1|v2        write outputs/<name>_*.html
"""

from __future__ import annotations

import argparse
import sys

from gridkeepup import config, manual
from gridkeepup.paths import DB_PATH, EIA860M_DIR, EIA930_DIR, OUTPUTS_DIR


def _count(folder, pattern: str) -> int:
    return len(list(folder.glob(pattern))) if folder.exists() else 0


def cmd_check(_: argparse.Namespace) -> int:
    key = "yes" if config.has_eia_api_key() else "NO (see .env.example)"
    print("EIA_API_KEY set:        ", key)
    print("EIA-930 files:          ", _count(EIA930_DIR, "*.csv"))
    print("EIA-860M workbooks:     ", _count(EIA860M_DIR, "*.xlsx"))
    print("DuckDB built:           ", "yes" if DB_PATH.exists() else "no")
    print("Unverified manual rows: ", manual.unverified_count())
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    hist = config.assumptions()["history"]
    region = config.assumptions()["region"]
    ok = True
    if args.source in ("eia930", "all"):
        from gridkeepup.fetch import eia930
        print(f"EIA-930 {region['eia_respondent']} {hist['first_year']}-{hist['last_year']}")
        failed = eia930.download(hist["first_year"], hist["last_year"],
                                 config.get_eia_api_key(), region["eia_respondent"],
                                 overwrite=args.overwrite)
        ok = ok and not failed
    if args.source in ("eia860m", "all"):
        from gridkeepup.fetch import eia860m
        print("EIA-860M")
        try:
            eia860m.download_latest()
        except RuntimeError as e:
            print(f"  FAILED: {e}")
            ok = False
    return 0 if ok else 1


def cmd_build(_: argparse.Namespace) -> int:
    from gridkeepup import store
    print(f"Building {DB_PATH.name}")
    store.build()
    return 0


def cmd_quality(_: argparse.Namespace) -> int:
    import pandas as pd

    from gridkeepup import clean
    from gridkeepup.fetch import eia930
    report = clean.quality_report(clean.clean_demand(eia930.load("demand")))
    if report.empty:
        print("No EIA-930 demand downloaded yet. Run `gridkeepup fetch eia930`.")
        return 1
    with pd.option_context("display.width", 120):
        print(report.to_string())
    return 0


def cmd_demand(_: argparse.Namespace) -> int:
    import pandas as pd

    from gridkeepup import demand
    a = demand.DemandAssumptions.from_config()
    with pd.option_context("display.width", 120):
        print("New data center load (excludes load already on the system):")
        print(demand.project(a).to_string(index=False))
        print(f"\nConnected GW by stage by {a.end_year}:")
        print(demand.by_stage(a).to_string())
    return 0


def cmd_crosscheck(_: argparse.Namespace) -> int:
    import pandas as pd

    from gridkeepup import epoch
    out = epoch.compare()
    if out.empty:
        print("Epoch data not found. Download it into data/raw/epoch/data_centers/.")
        return 1
    with pd.option_context("display.width", 160):
        print("New facility power since the energization pause (Epoch) vs new data center")
        print("load drawing power (model ramped_gw). Epoch is a subset, so model >= Epoch:")
        print(out.to_string(index=False))
    return 0


def cmd_supply(_: argparse.Namespace) -> int:
    import pandas as pd

    from gridkeepup import supply
    p = supply.project()
    if p.empty:
        print("No EIA-860M workbook found. Run `gridkeepup fetch eia860m`.")
        return 1
    with pd.option_context("display.width", 160):
        print("Total installed capacity, GW (net summer, expected values):")
        print(supply.totals(p).to_string())
        print("\nMid scenario by fuel, GW:")
        mid = p[p["scenario"] == "mid"].pivot(index="year", columns="fuel", values="capacity_gw")
        print(mid[supply.FUEL_ORDER].round(1).to_string())
        print(f"\nSources: {p.attrs['sources']}. Pipeline GW by source and stage, and what each")
        print("scenario counts by the horizon end:")
        print(supply.additions_by_stage().to_string())
    return 0


def cmd_derive(_: argparse.Namespace) -> int:
    from gridkeepup import derive, lbnl
    derived = derive.derive_all()
    if not derived:
        print("No raw data found (EIA-860M, LBNL). Download them first.")
        return 1
    for d in derived:
        print(f"{d.key} = {d.value:g}\n    inputs: {d.inputs}\n    method: {d.method}")
    e = lbnl.load_ercot()
    if not e.empty:
        derive.write_curves(e)
        print(f"\nwrote data/derived/{derive.CURVES_PATH.name}")
    derive.write_markdown(derived, derive.informational(e))
    print("wrote docs/derived-values.md")
    bad = derive.mismatches(derived)
    if bad:
        print("\nConfig does not match the data:\n  " + "\n  ".join(bad))
        return 1
    print("Config matches the data.")
    return 0


def cmd_adequacy(_: argparse.Namespace) -> int:
    import pandas as pd

    from gridkeepup import adequacy
    if adequacy.weather_profiles().empty:
        print("No hourly data. Run `gridkeepup fetch eia930` and `gridkeepup fetch eia860m`.")
        return 1
    out = adequacy.write_results()
    s, room = out["adequacy_summary"], out["adequacy_headroom"]
    a = adequacy.AdequacyAssumptions.from_config()
    with pd.option_context("display.width", 160):
        print(f"Expected loss-of-load events per year (standard: {a.standard}), weather years "
              f"{sorted(out['adequacy_by_weather_year']['weather_year'].unique())}:")
        print(s.pivot_table(index=["demand", "supply"], columns="year", values="lole")
              .round(2).to_string())
        print("\nShare of that risk in winter (Dec-Feb, incl. Uri-like storms), mid / mid:")
        print(s[(s.demand == "mid") & (s.supply == "mid")].set_index("year")["winter_share"]
              .round(2).to_string())
        print("\nRound-the-clock load the grid could add (+) or would need to shed in risky "
              "hours (-) to meet the standard, GW:")
        print(room.pivot_table(index=["demand", "supply"], columns="year",
                               values="headroom_gw").round(1).to_string())
    print("\nwrote data/derived/adequacy_*.csv")
    return 0


def cmd_chart(args: argparse.Namespace) -> int:
    from gridkeepup import charts
    OUTPUTS_DIR.mkdir(exist_ok=True)
    figs = {"v0": ("v0_queue_vs_peak.html", charts.v0_queue_vs_peak),
            "v1": ("v1_demand_scenarios.html", charts.v1_demand_scenarios),
            "v2": ("v2_supply_by_fuel.html", charts.v2_supply_by_fuel),
            "v3": ("v3_adequacy.html", charts.v3_adequacy)}
    name, make = figs[args.name]
    path = OUTPUTS_DIR / name
    make().write_html(path, include_plotlyjs="cdn")
    print(f"wrote {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gridkeepup", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    fetch = sub.add_parser("fetch")
    fetch.add_argument("source", choices=["eia930", "eia860m", "all"])
    fetch.add_argument("--overwrite", action="store_true", help="re-download existing years")
    fetch.set_defaults(fn=cmd_fetch)
    sub.add_parser("build").set_defaults(fn=cmd_build)
    sub.add_parser("quality").set_defaults(fn=cmd_quality)
    sub.add_parser("demand").set_defaults(fn=cmd_demand)
    sub.add_parser("crosscheck").set_defaults(fn=cmd_crosscheck)
    sub.add_parser("supply").set_defaults(fn=cmd_supply)
    sub.add_parser("derive").set_defaults(fn=cmd_derive)
    sub.add_parser("adequacy").set_defaults(fn=cmd_adequacy)
    chart = sub.add_parser("chart")
    chart.add_argument("name", choices=["v0", "v1", "v2", "v3"])
    chart.set_defaults(fn=cmd_chart)
    args = parser.parse_args(argv)
    try:
        return args.fn(args)
    except config.MissingKeyError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
