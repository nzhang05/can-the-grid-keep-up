"""v2 supply model: ERCOT installed capacity by fuel and year, per scenario.

    capacity(fuel, Y) = operating fleet today
                        - units with a planned retirement year <= Y
                        + sum over planned units of
                            P(built | EIA status, scenario)
                            x [planned year + delay(status, scenario) <= Y]

Capacity is net summer MW (what a unit can deliver in hot weather, when ERCOT peaks).
Values are expected values: a planned 500 MW unit with a 25% chance adds 125 MW.

Source: EIA-860M generator inventory, ERCOT balancing area (data/raw/eia860m/).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from gridkeepup import config
from gridkeepup.fetch import eia860m

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
    probability: dict[str, dict[str, float]]   # status -> scenario -> P(built)
    delay_years: dict[str, dict[str, int]]     # status -> scenario -> years added
    planned_storage_hours: float

    @classmethod
    def from_config(cls, cfg: dict | None = None) -> SupplyAssumptions:
        cfg = cfg or config.assumptions()
        s, h = cfg["supply"], cfg["horizon"]
        return cls(h["start_year"], h["end_year"], int(s["snapshot_year"]),
                   {k: {sc: float(v) for sc, v in d.items()}
                    for k, d in s["status_probability"].items()},
                   {k: {sc: int(v) for sc, v in d.items()}
                    for k, d in s["status_delay_years"].items()},
                   float(s["planned_storage_hours"]))

    @property
    def years(self) -> list[int]:
        return list(range(self.start_year, self.end_year + 1))


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


def project(inventory: dict[str, pd.DataFrame] | None = None,
            a: SupplyAssumptions | None = None) -> pd.DataFrame:
    """Expected installed capacity: scenario, year, fuel, capacity_gw, storage_gwh."""
    a = a or SupplyAssumptions.from_config()
    inventory = inventory if inventory is not None else eia860m.load_latest()
    if not inventory:
        return pd.DataFrame(columns=["scenario", "year", "fuel", "capacity_gw", "storage_gwh"])
    op, pl = prepare(inventory)
    unknown = set(pl["status_code"]) - set(a.probability)
    if unknown:
        raise ValueError(f"No probability configured for EIA status codes {sorted(unknown)}")

    op_storage_hours = (op.loc[op["fuel"] == "Storage", "mwh"].sum()
                        / max(op.loc[op["fuel"] == "Storage", "mw"].sum(), 1e-9))
    rows = []
    for scenario in SCENARIOS:
        p = pl["status_code"].map({c: v[scenario] for c, v in a.probability.items()})
        delay = pl["status_code"].map({c: v[scenario] for c, v in a.delay_years.items()})
        arrives = pl["online_year"] + delay
        for year in a.years:
            existing = op[~(op["retire_year"] <= year)]
            new = pl.assign(exp_mw=pl["mw"] * p)[arrives <= year]
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
    return out


def totals(proj: pd.DataFrame) -> pd.DataFrame:
    """Total GW by scenario and year."""
    return proj.pivot_table(index="year", columns="scenario", values="capacity_gw",
                            aggfunc="sum")[list(SCENARIOS)].round(1)


def additions_by_status(inventory: dict[str, pd.DataFrame] | None = None,
                        a: SupplyAssumptions | None = None) -> pd.DataFrame:
    """Planned GW by EIA status, and the expected GW each scenario counts by horizon end."""
    a = a or SupplyAssumptions.from_config()
    inventory = inventory if inventory is not None else eia860m.load_latest()
    _, pl = prepare(inventory)
    out = pl.groupby("status_code")["mw"].sum().div(1000).rename("planned_gw").to_frame()
    for scenario in SCENARIOS:
        arrives = pl["online_year"] + pl["status_code"].map(
            {c: v[scenario] for c, v in a.delay_years.items()})
        p = pl["status_code"].map({c: v[scenario] for c, v in a.probability.items()})
        counted = (pl["mw"] * p)[arrives <= a.end_year]
        out[f"{scenario}_counted_gw"] = counted.groupby(pl["status_code"]).sum().div(1000)
    return out.fillna(0.0).round(2)
