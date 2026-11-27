"""v2 supply model: ERCOT installed capacity by fuel and year, per scenario.

    capacity(fuel, Y) = operating fleet today (EIA-860M)
                        - units with a planned retirement year <= Y
                        + sum over new projects of
                            P(built | stage, scenario) x [online year + delay <= Y]

New projects come from two sources, split by year so nothing is counted twice:
EIA-860M planned units up to ``ercot_gis.first_year - 1`` (stage = EIA status), and
ERCOT's interconnection queue from ``ercot_gis.first_year`` (stage = furthest milestone;
odds for signed agreements depend on fuel; nameplate MW converted to summer MW).

Capacity is net summer MW (what a unit can deliver in hot weather, when ERCOT peaks).
Values are expected values: a planned 500 MW unit with a 25% chance adds 125 MW.

Source: EIA-860M generator inventory, ERCOT balancing area (data/raw/eia860m/).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from gridkeepup import config
from gridkeepup.fetch import eia860m, ercot_gis

SCENARIOS = ("low", "mid", "high")

# EIA technology -> fuel group used in charts and the adequacy model.
FUEL_GROUPS = {
    "Natural Gas Fired Combined Cycle": "Gas",
    "Natural Gas Fired Combustion Turbine": "Gas",
    "Natural Gas Steam Turbine": "Gas",
    "Natural Gas Internal Combustion Engine": "Gas",
    "Natural Gas with Compressed Air Storage": "Gas",
    "Other Natural Gas": "Gas",
    "Conventional Steam Coal": "Coal",
    "Petroleum Coke": "Coal",
    "Nuclear": "Nuclear",
    "Onshore Wind Turbine": "Wind",
    "Offshore Wind Turbine": "Wind",
    "Solar Photovoltaic": "Solar",
    "Solar Thermal with Energy Storage": "Solar",
    "Solar Thermal without Energy Storage": "Solar",
    "Batteries": "Storage",
    "Flywheels": "Storage",
    "Hydroelectric Pumped Storage": "Storage",
    "Conventional Hydroelectric": "Hydro",
}
OTHER = "Other"   # petroleum, biomass, landfill gas, "All Other"
FUEL_ORDER = ["Nuclear", "Coal", "Gas", "Wind", "Solar", "Storage", "Hydro", OTHER]


def fuel_group(technology: str) -> str:
    return FUEL_GROUPS.get(str(technology).strip(), OTHER)


def status_code(status: str) -> str:
    """'(U) Under construction, ...' -> 'U'."""
    s = str(status).strip()
    return s[1:s.index(")")] if s.startswith("(") and ")" in s else s


@dataclass(frozen=True)
class SupplyAssumptions:
    start_year: int
    end_year: int
    snapshot_year: int
    probability: dict[str, dict[str, float]]   # EIA status -> scenario -> P(built)
    delay_years: dict[str, dict[str, int]]     # EIA status -> scenario -> years added
    planned_storage_hours: float
    gis_enabled: bool
    gis_first_year: int
    gis_probability: dict                      # stage -> scenario -> P, or "signed" -> fuel -> ...
    gis_delay_years: dict[str, dict[str, int]]
    summer_ratio: dict[str, float]
    gis_timing: str = "curves"
    tax_credit: dict | None = None

    @classmethod
    def from_config(cls, cfg: dict | None = None) -> SupplyAssumptions:
        cfg = cfg or config.assumptions()
        s, h = cfg["supply"], cfg["horizon"]
        g = s["ercot_gis"]
        return cls(h["start_year"], h["end_year"], int(s["snapshot_year"]),
                   {k: {sc: float(v) for sc, v in d.items()}
                    for k, d in s["status_probability"].items()},
                   {k: {sc: int(v) for sc, v in d.items()}
                    for k, d in s["status_delay_years"].items()},
                   float(s["planned_storage_hours"]),
                   bool(g.get("enabled", True)), int(g["first_year"]), g["stage_probability"],
                   {k: {sc: int(v) for sc, v in d.items()}
                    for k, d in g["stage_delay_years"].items()},
                   {k: float(v) for k, v in g["summer_ratio"].items()},
                   str(g.get("timing", "curves")),
                   g.get("tax_credit_factor"))

    @property
    def years(self) -> list[int]:
        return list(range(self.start_year, self.end_year + 1))

    def gis_p(self, stage: str, fuel: str, scenario: str) -> float:
        table = self.gis_probability[stage]
        if stage in CURVE_STAGES:
            table = table.get(fuel, table["Other"])
        p = float(table[scenario])
        tc = self.tax_credit
        if tc and fuel in tc["fuels"] and stage in tc["stages"]:
            p *= float(tc[scenario])
        return p


CURVE_STAGES = {"signed": ("signed", "ia_year"), "study": ("queue", "queue_year")}


def load_curves(path=None) -> pd.DataFrame:
    from gridkeepup.paths import DERIVED_DIR
    path = path or DERIVED_DIR / "completion_curves.csv"
    return pd.read_csv(path)


def online_by(curve: pd.Series, age: int, years_ahead: int, level: float) -> float:
    """P(online within ``years_ahead`` more years | not online at ``age``).

    ``curve`` is cumulative share online by year k (index k). It is rescaled so its plateau
    equals ``level`` (shape from history, level from the decided eventual odds), then
    conditioned on not being online yet.
    """
    if years_ahead <= 0:
        return 0.0
    kmax = int(curve.index.max())
    peak = float(curve.max())
    if peak <= 0:
        return 0.0
    g = (curve / peak * level).clip(upper=1.0)
    g_now = float(g.loc[min(max(age, 0), kmax)])
    g_then = float(g.loc[min(max(age, 0) + years_ahead, kmax)])
    return max(0.0, (g_then - g_now) / (1.0 - g_now)) if g_now < 1 else 0.0


def _year(col: pd.Series) -> pd.Series:
    return pd.to_numeric(col, errors="coerce")   # EIA uses ' ' for "no date"


def prepare(inventory: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(operating, planned) with fuel group, years and summer MW cleaned."""
    op = inventory["operating"].copy()
    op["fuel"] = op["technology"].map(fuel_group)
    op["retire_year"] = _year(op["planned_retirement_year"])
    op["mw"] = pd.to_numeric(op["net_summer_capacity_mw"], errors="coerce").fillna(0.0)
    op["mwh"] = pd.to_numeric(op.get("nameplate_energy_capacity_mwh"), errors="coerce")

    pl = inventory["planned"].copy()
    pl["fuel"] = pl["technology"].map(fuel_group)
    pl["status_code"] = pl["status"].map(status_code)
    pl["online_year"] = _year(pl["planned_operation_year"])
    pl["mw"] = pd.to_numeric(pl["net_summer_capacity_mw"], errors="coerce").fillna(0.0)
    return op, pl


def pipeline(inventory: dict[str, pd.DataFrame], gis: pd.DataFrame | None,
             a: SupplyAssumptions, scenario: str,
             curves: pd.DataFrame | None = None) -> pd.DataFrame:
    """Every new project with its source, stage, fuel, summer MW, P(built) and arrival year."""
    _, pl = prepare(inventory)
    unknown = set(pl["status_code"]) - set(a.probability)
    if unknown:
        raise ValueError(f"No probability configured for EIA status codes {sorted(unknown)}")
    use_gis = a.gis_enabled and gis is not None and not gis.empty
    if use_gis:
        pl = pl[pl["online_year"] < a.gis_first_year]
    eia = pd.DataFrame({
        "source": "EIA-860M",
        "stage": pl["status_code"],
        "fuel": pl["fuel"],
        "mw": pl["mw"],
        "p": pl["status_code"].map({c: v[scenario] for c, v in a.probability.items()}),
        "arrives": pl["online_year"] + pl["status_code"].map(
            {c: v[scenario] for c, v in a.delay_years.items()}),
    })
    if not use_gis:
        return eia.reset_index(drop=True)
    g = gis[gis["cod_year"] >= a.gis_first_year].copy()
    unknown = set(g["stage"]) - set(a.gis_probability)
    if unknown:
        raise ValueError(f"No probability configured for ERCOT GIS stages {sorted(unknown)}")
    g["mw"] = g["mw_nameplate"] * g["fuel"].map(lambda f: a.summer_ratio.get(f, 1.0))
    timed = g["stage"].isin(CURVE_STAGES) if a.gis_timing == "curves" else g["stage"].isna()
    fixed = g[~timed]
    parts = [eia, pd.DataFrame({
        "source": "ERCOT GIS",
        "stage": fixed["stage"],
        "fuel": fixed["fuel"],
        "mw": fixed["mw"],
        "p": [a.gis_p(st, f, scenario) for st, f in zip(fixed["stage"], fixed["fuel"],
                                                          strict=True)],
        "arrives": fixed["cod_year"] + fixed["stage"].map(
            {k: v[scenario] for k, v in a.gis_delay_years.items()}).astype(float),
    })]
    if timed.any():
        parts.append(_curve_timed(g[timed], a, scenario, curves))
    return pd.concat(parts, ignore_index=True)


def _curve_timed(g: pd.DataFrame, a: SupplyAssumptions, scenario: str,
                 curves: pd.DataFrame | None) -> pd.DataFrame:
    """One row per project and arrival year, with that year's increment in P(online)."""
    curves = load_curves() if curves is None else curves
    lookup = {key: grp.set_index("k")["share"]
              for key, grp in curves.groupby(["basis", "fuel"])}
    rows = []
    for r in g.itertuples(index=False):
        basis, start_col = CURVE_STAGES[r.stage]
        curve = lookup.get((basis, r.fuel), lookup[(basis, "All")])
        start = getattr(r, start_col)
        age = a.snapshot_year - int(start) if pd.notna(start) else 0
        level = a.gis_p(r.stage, r.fuel, scenario)
        prev = 0.0
        for year in range(a.snapshot_year + 1, a.end_year + 1):
            p = online_by(curve, age, year - a.snapshot_year, level) if year >= r.cod_year else 0.0
            if p > prev:
                rows.append({"source": "ERCOT GIS", "stage": r.stage, "fuel": r.fuel,
                             "mw": r.mw, "p": p - prev, "arrives": year})
                prev = p
    return pd.DataFrame(rows, columns=["source", "stage", "fuel", "mw", "p", "arrives"])


def project(inventory: dict[str, pd.DataFrame] | None = None,
            a: SupplyAssumptions | None = None,
            gis: pd.DataFrame | None = None) -> pd.DataFrame:
    """Expected installed capacity: scenario, year, fuel, capacity_gw, storage_gwh.

    ``gis=None`` loads the latest ERCOT GIS report if one is on disk; pass an empty frame
    to use EIA-860M only.
    """
    a = a or SupplyAssumptions.from_config()
    inventory = inventory if inventory is not None else eia860m.load_latest()
    if not inventory:
        return pd.DataFrame(columns=["scenario", "year", "fuel", "capacity_gw", "storage_gwh"])
    gis = ercot_gis.load_latest() if gis is None else gis
    op, _ = prepare(inventory)
    op_storage_hours = (op.loc[op["fuel"] == "Storage", "mwh"].sum()
                        / max(op.loc[op["fuel"] == "Storage", "mw"].sum(), 1e-9))
    rows = []
    for scenario in SCENARIOS:
        new_all = pipeline(inventory, gis, a, scenario)
        new_all = new_all.assign(exp_mw=new_all["mw"] * new_all["p"])
        for year in a.years:
            existing = op[~(op["retire_year"] <= year)]
            new = new_all[new_all["arrives"] <= year]
            by_fuel = (existing.groupby("fuel")["mw"].sum()
                       .add(new.groupby("fuel")["exp_mw"].sum(), fill_value=0.0))
            storage_gwh = (existing.loc[existing["fuel"] == "Storage", "mwh"].sum()
                           + new.loc[new["fuel"] == "Storage", "exp_mw"].sum()
                           * a.planned_storage_hours) / 1000
            for fuel in FUEL_ORDER:
                rows.append({"scenario": scenario, "year": year, "fuel": fuel,
                             "capacity_gw": by_fuel.get(fuel, 0.0) / 1000,
                             "storage_gwh": storage_gwh if fuel == "Storage" else 0.0})
    out = pd.DataFrame(rows).round(3)
    out.attrs["operating_storage_hours"] = round(float(op_storage_hours), 2)
    today = op.groupby("fuel")["mw"].sum().div(1000)
    out.attrs["today_by_fuel_gw"] = {f: round(float(today.get(f, 0.0)), 3) for f in FUEL_ORDER}
    out.attrs["sources"] = "EIA-860M + ERCOT GIS" if a.gis_enabled and not gis.empty \
        else "EIA-860M only"
    return out


def totals(proj: pd.DataFrame) -> pd.DataFrame:
    """Total GW by scenario and year."""
    return proj.pivot_table(index="year", columns="scenario", values="capacity_gw",
                            aggfunc="sum")[list(SCENARIOS)].round(1)


def additions_by_stage(inventory: dict[str, pd.DataFrame] | None = None,
                       a: SupplyAssumptions | None = None,
                       gis: pd.DataFrame | None = None) -> pd.DataFrame:
    """Pipeline GW (summer) by source and stage, and the expected GW counted by horizon end."""
    a = a or SupplyAssumptions.from_config()
    inventory = inventory if inventory is not None else eia860m.load_latest()
    gis = ercot_gis.load_latest() if gis is None else gis
    out = None
    for scenario in SCENARIOS:
        pipe = pipeline(inventory, gis, a, scenario)
        if out is None:
            out = pipe.groupby(["source", "stage"])["mw"].sum().div(1000).rename("pipeline_gw") \
                .to_frame()
        counted = (pipe["mw"] * pipe["p"])[pipe["arrives"] <= a.end_year]
        out[f"{scenario}_counted_gw"] = counted.groupby(
            [pipe["source"], pipe["stage"]]).sum().div(1000)
    return out.fillna(0.0).round(2)


def _norm_name(s: str) -> str:
    s = str(s).lower()
    for word in ("energy", "storage", "solar", "wind", "bess", "project", "center", "llc",
                 "generating", "station", "power", "plant"):
        s = s.replace(word, "")
    return re.sub(r"[^a-z0-9]", "", s)


def boundary_overlap(inventory: dict[str, pd.DataFrame] | None = None,
                     a: SupplyAssumptions | None = None,
                     gis: pd.DataFrame | None = None) -> pd.DataFrame:
    """Projects EIA lists before the split year that ERCOT lists from it (double-count risk).

    Matched on normalised name and county; name matching is loose, so treat the result as
    an indication, not an exact count.
    """
    a = a or SupplyAssumptions.from_config()
    inventory = inventory if inventory is not None else eia860m.load_latest()
    gis = ercot_gis.load_latest() if gis is None else gis
    _, pl = prepare(inventory)
    eia = pl[pl["online_year"] < a.gis_first_year].assign(
        key=lambda d: d["plant_name"].map(_norm_name),
        county_key=lambda d: d["county"].astype(str).str.lower().str.strip())
    eia = eia[eia["key"] != ""]
    late = gis[gis["cod_year"] >= a.gis_first_year].assign(
        key=lambda d: d["project_name"].map(_norm_name),
        county_key=lambda d: d["county"].str.lower())
    m = late.merge(eia[["key", "county_key", "plant_name", "online_year"]].drop_duplicates(),
                   on=["key", "county_key"])
    return m[["inr", "project_name", "plant_name", "county", "fuel", "stage", "cod_year",
              "online_year", "mw_nameplate"]]
