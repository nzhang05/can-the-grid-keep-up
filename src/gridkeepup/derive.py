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
from gridkeepup.paths import DERIVED_DIR, ROOT

CURVES_PATH = DERIVED_DIR / "completion_curves.csv"


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


def study_odds(e: pd.DataFrame) -> list[Derived]:
    """Eventual completion for queue projects still in study: same rule, all-request history."""
    shares = lbnl.request_shares(e)
    odds = lbnl.odds_from_shares(shares)
    out = []
    for fuel, row in (("Wind", "Wind"), ("Gas", "Gas"), ("Solar", "Solar"),
                      ("Storage", "Storage"), ("Other", "All")):
        s = shares.loc[row]
        label = "all fuels" if row == "All" else fuel.lower()
        for scen in ("low", "mid", "high"):
            out.append(Derived(
                f"supply.ercot_gis.stage_probability.study.{fuel}.{scen}",
                float(odds.loc[row, scen]),
                f"ERCOT {label} requests submitted 2000-2020 ({s['gw']:.1f} GW): "
                f"{s['operational']:.1%} operating, {s['active']:.1%} still in progress, "
                f"{s['withdrawn']:.1%} withdrawn at end-2025",
                {"low": "operating share", "mid": "operating + half of still in progress",
                 "high": "operating + all still in progress"}[scen],
                e.attrs.get("source_file", "LBNL")))
    return out


def completion_curves(e: pd.DataFrame) -> pd.DataFrame:
    """Timing curves: share online within k years of signing (``signed``) or queue entry."""
    parts = []
    for basis, col in (("signed", "ia_date"), ("queue", "q_date")):
        c = lbnl.completion_curve(e, col)
        c.insert(0, "basis", basis)
        parts.append(c)
    return pd.concat(parts, ignore_index=True)


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
        out += completion_odds(e) + study_odds(e) + anchor_rates(e)
    return out


def curves_mismatch(e: pd.DataFrame | None = None) -> str | None:
    """None if the committed curves CSV equals what the data gives, else a message."""
    e = lbnl.load_ercot() if e is None else e
    fresh = completion_curves(e)
    if not CURVES_PATH.exists():
        return f"{CURVES_PATH.name} missing: run `gridkeepup derive`"
    saved = pd.read_csv(CURVES_PATH)
    merged = fresh.merge(saved, on=["basis", "fuel", "k"], suffixes=("", "_saved"), how="outer")
    diff = (merged["share"] - merged["share_saved"]).abs().max()
    if merged["share_saved"].isna().any() or diff > 1e-6:
        return f"{CURVES_PATH.name} does not match the data: run `gridkeepup derive`"
    return None


def write_curves(e: pd.DataFrame) -> pd.DataFrame:
    c = completion_curves(e)
    CURVES_PATH.parent.mkdir(parents=True, exist_ok=True)
    c.to_csv(CURVES_PATH, index=False)
    return c


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


def backtest(e: pd.DataFrame, snapshot: int, years: int = 4) -> pd.DataFrame:
    """Replay the queue timing method on ERCOT's queue as it stood at the end of ``snapshot``.

    Curves are rebuilt from data up to ``snapshot`` only; eventual odds are the configured mid
    values without the tax-credit factor (no such policy existed then). Every project still in
    the queue (not online, not withdrawn) is treated as signed or study, so projects already
    under construction are under-counted in the first year. Returns model vs actual GW by year.
    """
    from gridkeepup import supply

    a = supply.SupplyAssumptions.from_config()
    end = pd.Timestamp(f"{snapshot}-12-31")
    curves = {}
    for basis, col in (("signed", "ia_date"), ("queue", "q_date")):
        for fuel, grp in lbnl.completion_curve(e, col, data_year=snapshot).groupby("fuel"):
            curves[(basis, fuel)] = grp.set_index("k")["share"]
    gone = e["wd_date"].le(end) | (e["q_status"].isin(["withdrawn", "suspended"])
                                   & e["wd_date"].isna())
    q = e[e["q_date"].le(end) & ~e["on_date"].le(end) & ~gone & e["mw"].gt(0)]
    rows = []
    for r in q.itertuples(index=False):
        signed = pd.notna(r.ia_date) and r.ia_date <= end
        stage, basis, start = ("signed", "signed", r.ia_date) if signed else \
            ("study", "queue", r.q_date)
        fuel = r.fuel if r.fuel in ("Wind", "Gas", "Solar", "Storage") else "Other"
        curve = curves.get((basis, fuel), curves[(basis, "All")])
        level = float(a.gis_probability[stage].get(fuel, a.gis_probability[stage]["Other"])["mid"])
        prev = 0.0
        for y in range(snapshot + 1, snapshot + years + 1):
            ok = pd.isna(r.prop_date) or y >= r.prop_date.year
            p = supply.online_by(curve, snapshot - start.year, y - snapshot, level) if ok else 0
            p = max(p, prev)
            rows.append((y, r.mw * (p - prev) / 1000))
            prev = p
    out = pd.DataFrame(rows, columns=["year", "model_gw"]).groupby("year").sum()
    on = q[q["on_date"].dt.year.between(snapshot + 1, snapshot + years)]
    out["actual_gw"] = on.groupby(on["on_date"].dt.year)["mw"].sum() / 1000
    return out.fillna(0)


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
    for snap in (2019, 2020, 2021):
        b = backtest(e, snap)
        m, act = b.model_gw.sum(), b.actual_gw.sum()
        lines.append(f"Backtest of the queue timing method on ERCOT's queue at end-{snap}: model "
                     f"{m:.1f} GW vs actual {act:.1f} GW added in {snap + 1}-{snap + 4} "
                     f"(actual / model {act / m:.2f})")
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
    curves = ""
    if CURVES_PATH.exists():
        c = pd.read_csv(CURVES_PATH)
        curves = ("\n## Completion timing curves\n\n"
                  "Share of ERCOT capacity online within k years of signing an interconnection "
                  "agreement (`signed`) or entering the queue (`queue`). Only cohorts with k full "
                  "years of follow-up count (start year <= 2025 - k); capacity-weighted; made "
                  "non-decreasing; a year with under 0.5 GW of sample repeats the previous value. "
                  f"Full table: `data/derived/{CURVES_PATH.name}`.\n\n")
        for basis in ("signed", "queue"):
            w = c[c["basis"] == basis].pivot(index="fuel", columns="k", values="share")
            n = c[c["basis"] == basis].pivot(index="fuel", columns="k", values="sample_gw")
            ks = [k for k in w.columns if 1 <= k <= 8]
            curves += f"**{basis}** (share online by year k; sample GW in brackets)\n\n"
            curves += "| Fuel | " + " | ".join(f"k={k}" for k in ks) + " |\n"
            curves += "| --- | " + " | ".join("---" for _ in ks) + " |\n"
            for fuel in w.index:
                curves += f"| {fuel} | " + " | ".join(
                    f"{w.loc[fuel, k]:.0%} ({n.loc[fuel, k]:.1f})" for k in ks) + " |\n"
            curves += "\n"
    return head + rows + tail + curves


def write_markdown(derived: list[Derived], extra: str = "") -> None:
    (ROOT / "docs" / "derived-values.md").write_text(to_markdown(derived, extra), encoding="utf-8")
