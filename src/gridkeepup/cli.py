"""Command line entry point: `uv run gridkeepup <command>`.

  check                 what's configured and which inputs are on disk
  fetch eia930          hourly ERCOT demand and generation by fuel (needs EIA_API_KEY)
  fetch eia860m         latest EIA-860M generator inventory
  fetch all             both of the above
  build                 load every input into data/grid.duckdb
  quality               per-year data quality report for hourly demand
  demand                v1 data center demand scenarios (from config/assumptions.yaml)
  crosscheck            compare the demand model with Epoch AI's Texas data centers
  chart v0|v1           write outputs/<name>_*.html
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


def cmd_chart(args: argparse.Namespace) -> int:
    from gridkeepup import charts
    OUTPUTS_DIR.mkdir(exist_ok=True)
    figs = {"v0": ("v0_queue_vs_peak.html", charts.v0_queue_vs_peak),
            "v1": ("v1_demand_scenarios.html", charts.v1_demand_scenarios)}
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
    chart = sub.add_parser("chart")
    chart.add_argument("name", choices=["v0", "v1"])
    chart.set_defaults(fn=cmd_chart)
    args = parser.parse_args(argv)
    try:
        return args.fn(args)
    except config.MissingKeyError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
