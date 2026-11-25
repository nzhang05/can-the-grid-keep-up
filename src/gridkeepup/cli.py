"""Command line entry point: `uv run gridkeepup <command>`.

  check                 what's configured and which inputs are on disk
  fetch eia930          hourly ERCOT demand and generation by fuel (needs EIA_API_KEY)
  fetch eia860m         latest EIA-860M generator inventory
  fetch all             both of the above
  build                 load every input into data/grid.duckdb
  chart v0              write outputs/v0_queue_vs_peak.html
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


def cmd_chart(args: argparse.Namespace) -> int:
    from gridkeepup import charts
    OUTPUTS_DIR.mkdir(exist_ok=True)
    if args.name == "v0":
        path = OUTPUTS_DIR / "v0_queue_vs_peak.html"
        charts.v0_queue_vs_peak().write_html(path, include_plotlyjs="cdn")
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
    chart = sub.add_parser("chart")
    chart.add_argument("name", choices=["v0"])
    chart.set_defaults(fn=cmd_chart)
    args = parser.parse_args(argv)
    try:
        return args.fn(args)
    except config.MissingKeyError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
