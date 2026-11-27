"""Every value in the config that is computed from data, recomputed from the raw files.

`gridkeepup derive` prints each derived value with its inputs and method, writes
docs/derived-values.md, and reports any config value that no longer matches the data.
tests/test_derived_values.py runs the same check (skipped when the raw files are absent).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pandas as pd

from gridkeepup import config, lbnl, supply
from gridkeepup.fetch import eia860m
from gridkeepup.paths import ROOT


@dataclass
class Derived:
    key: str            # config path, e.g. "supply.planned_storage_hours"
    value: float
    inputs: str         # the numbers that went in
    method: str         # how they were combined
    source: str         # file it came from


def storage_hours(op: pd.DataFrame) -> Derived:
    b = op[op["technology"] == "Batteries"]
    mwh = pd.to_numeric(b["nameplate_energy_capacity_mwh"], errors="coerce").sum()
    mw = pd.to_numeric(b["nameplate_capacity_mw"], errors="coerce").sum()
    return Derived("supply.planned_storage_hours", round(mwh / mw, 1),
                   f"{len(b)} operating ERCOT batteries: {mwh:,.0f} MWh energy, {mw:,.0f} MW "
                   "nameplate power",
                   "fleet average duration = total MWh / total MW, rounded to 0.1 h",
                   op.attrs.get("source_file") or str(op["source_file"].iloc[0]))


def summer_ratios(op: pd.DataFrame) -> list[Derived]:
    op = op.assign(fuel=op["technology"].map(supply.fuel_group))
    g = op.groupby("fuel")[["net_summer_capacity_mw", "nameplate_capacity_mw"]].sum()
    out = []
    for fuel in ("Gas", "Solar", "Wind", "Storage"):
        summer, name = g.loc[fuel, "net_summer_capacity_mw"], g.loc[fuel, "nameplate_capacity_mw"]
        out.append(Derived(f"supply.ercot_gis.summer_ratio.{fuel}", round(summer / name, 2),
                           f"operating ERCOT {fuel.lower()}: {summer:,.0f} MW net summer, "
                           f"{name:,.0f} MW nameplate",
                           "net summer MW / nameplate MW, rounded to 0.01",
                           str(op["source_file"].iloc[0])))
    return out


def completion_odds(e: pd.DataFrame) -> list[Derived]:
    shares = lbnl.post_agreement_shares(e)
    odds = lbnl.odds_from_shares(shares)
    out = []
    # "Other" (nuclear, hydro, other fuels in the queue) uses the all-ERCOT rate.
    for fuel, row in (("Wind", "Wind"), ("Gas", "Gas"), ("Solar", "Solar"),
                      ("Storage", "Storage"), ("Other", "All")):
        s = shares.loc[row]
        label = "all fuels" if row == "All" else fuel.lower()
        for scen in ("low", "mid", "high"):
            out.append(Derived(
                f"supply.ercot_gis.stage_probability.signed.{fuel}.{scen}",
                float(odds.loc[row, scen]),
                f"ERCOT {label} with agreements signed 2000-2022 ({s['gw']:.1f} GW): "
                f"{s['operational']:.1%} operating, {s['active']:.1%} still in progress, "
                f"{s['withdrawn']:.1%} withdrawn at end-2025",
                {"low": "operating share", "mid": "operating + half of still in progress",
                 "high": "operating + all still in progress"}[scen],
                e.attrs.get("source_file", "LBNL")))
    return out


def anchor_rates(e: pd.DataFrame) -> list[Derived]:
    """The ERCOT-wide rates the EIA status odds T (mid) and P (mid) are anchored on."""
    pa, rq = lbnl.post_agreement_shares(e).loc["All"], lbnl.request_shares(e).loc["All"]
    src = e.attrs.get("source_file", "LBNL")
    return [
        Derived("supply.status_probability.T.mid", round(pa["operational"], 2),
                f"all ERCOT capacity with agreements signed 2000-2022 ({pa['gw']:.1f} GW): "
                f"{pa['operational']:.1%} operating at end-2025",
                "operating share, rounded to 0.01", src),
        Derived("supply.status_probability.P.mid", round(rq["operational"], 2),
                f"all ERCOT requests submitted 2000-2020 ({rq['gw']:.1f} GW): "
                f"{rq['operational']:.1%} operating at end-2025",
                "operating share, rounded to 0.01", src),
    ]


def derive_all() -> list[Derived]:
    out: list[Derived] = []
    inv = eia860m.load_latest()
    if inv:
        op = inv["operating"]
        out += [storage_hours(op)] + summer_ratios(op)
    e = lbnl.load_ercot()
    if not e.empty:
        out += completion_odds(e) + anchor_rates(e)
    return out


def config_value(key: str, cfg: dict | None = None):
    node = cfg or config.assumptions()
    for part in key.split("."):
        node = node[part]
    return node


def mismatches(derived: list[Derived], cfg: dict | None = None) -> list[str]:
    bad = []
    for d in derived:
        try:
            got = float(config_value(d.key, cfg))
        except (KeyError, TypeError):
            bad.append(f"{d.key}: missing from config (data says {d.value})")
            continue
        if abs(got - d.value) > 1e-9:
            bad.append(f"{d.key}: config {got}, data says {d.value}")
    return bad


def informational(e: pd.DataFrame) -> str:
    """Numbers quoted in the docs but not stored in the config."""
    if e.empty:
        return ""
    years = lbnl.agreement_to_operation_years(e).round(1)
    rq = lbnl.request_shares(e).round(3)
    lines = ["Median years from signed agreement to operation (ERCOT, agreements 2000-2022, "
             "completed projects): " + ", ".join(f"{f.lower()} {v}" for f, v in years.items()),
             "All ERCOT requests 2000-2020, share operating / still in progress / withdrawn: "
             + ", ".join(f"{f.lower()} {r.operational:.0%} / {r.active:.0%} / {r.withdrawn:.0%}"
                         for f, r in rq.iterrows())]
    return "\n".join(f"- {line}" for line in lines)


def to_markdown(derived: list[Derived], extra: str = "") -> str:
    head = ("# Derived values\n\n"
            f"Generated by `uv run gridkeepup derive` on {dt.date.today():%Y-%m-%d}. Do not edit "
            "by hand: rerun the command after new data arrives. Each row is a value in "
            "`config/assumptions.yaml` that is computed from data; a test fails if the config "
            "and the data disagree.\n\n"
            "| Config value | Value | Inputs | Method | Source file |\n"
            "| --- | --- | --- | --- | --- |\n")
    rows = "".join(f"| `{d.key}` | {d.value:g} | {d.inputs} | {d.method} | {d.source} |\n"
                   for d in derived)
    tail = f"\n## Also from the data (quoted in the docs, not in the config)\n\n{extra}\n" \
        if extra else ""
    return head + rows + tail


def write_markdown(derived: list[Derived], extra: str = "") -> None:
    (ROOT / "docs" / "derived-values.md").write_text(to_markdown(derived, extra), encoding="utf-8")
