"""v1 demand model: how much new data center load reaches the ERCOT grid each year.

For each scenario (low / mid / high) and each queue stage:

    connected MW = stage GW x P(connect by horizon end) x data center share

Connected MW is spread evenly over the stage's connection years. Each year's cohort then
ramps linearly to full load over ``ramp_years`` (mid-year convention: a project drawing
for half of its first year counts 0.5 / ramp_years). Load already on the system
(``in_baseline``) is skipped: it is already in EIA's historical demand.

Outputs per scenario and year:

* connected_gw  nameplate of new data centers connected so far
* ramped_gw     nameplate actually energized after ramp-up
* avg_gw        average draw (ramped x load factor), for energy
* peak_gw       draw during system peak hours (ramped x peak factor), for adequacy
* energy_twh    avg_gw x hours in the year
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from gridkeepup import config

SCENARIOS = ("low", "mid", "high")


@dataclass(frozen=True)
class Stage:
    name: str
    gw: float
    p_connect: dict[str, float]
    in_baseline: bool = False
    connect_years: tuple[int, ...] = field(default_factory=tuple)
    ramp_years: float | None = None   # overrides the global ramp for this stage


@dataclass(frozen=True)
class DemandAssumptions:
    stages: tuple[Stage, ...]
    start_year: int
    end_year: int
    first_new_connection_year: int
    ramp_years: float
    load_factor: float
    peak_factor: float
    datacenter_share: float
    include_crypto: bool

    @classmethod
    def from_config(cls, cfg: dict | None = None) -> DemandAssumptions:
        cfg = cfg or config.assumptions()
        d, h = cfg["demand"], cfg["horizon"]
        first = d["first_new_connection_year"]
        stages = tuple(
            Stage(
                name=s["name"],
                gw=float(s["gw"]),
                p_connect={k: float(v) for k, v in s["p_connect"].items()},
                in_baseline=bool(s.get("in_baseline", False)),
                connect_years=tuple(s.get("connect_years")
                                    or range(first, h["end_year"] + 1)),
                ramp_years=float(s["ramp_years"]) if s.get("ramp_years") else None,
            )
            for s in d["stages"]
        )
        return cls(stages, h["start_year"], h["end_year"], first, float(d["ramp_years"]),
                   float(d["load_factor"]), float(d["peak_factor"]),
                   float(d["datacenter_share"]), bool(d["include_crypto"]))

    @property
    def years(self) -> list[int]:
        return list(range(self.start_year, self.end_year + 1))


def ramp_fraction(years_since_connection: int, ramp_years: float) -> float:
    """Share of nameplate drawn, on average, in the k-th year after connection (k=0 first)."""
    if years_since_connection < 0:
        return 0.0
    return min((years_since_connection + 0.5) / ramp_years, 1.0)


def _hours(year: int) -> int:
    return 8784 if pd.Timestamp(year=year, month=1, day=1).is_leap_year else 8760


def cohorts(a: DemandAssumptions, scenario: str) -> pd.DataFrame:
    """One row per (stage, connection year): GW of data centers connecting then, and ramp."""
    share = 1.0 if a.include_crypto else a.datacenter_share
    rows = []
    for s in a.stages:
        if s.in_baseline:
            continue
        connected = s.gw * s.p_connect[scenario] * share
        years = [y for y in s.connect_years if a.start_year <= y <= a.end_year]
        for y in years:
            rows.append({"stage": s.name, "connect_year": y, "gw": connected / len(years),
                         "ramp_years": s.ramp_years or a.ramp_years})
    return pd.DataFrame(rows, columns=["stage", "connect_year", "gw", "ramp_years"])


def project(a: DemandAssumptions | None = None) -> pd.DataFrame:
    """New data center load by scenario and year (see module docstring for columns)."""
    a = a or DemandAssumptions.from_config()
    rows = []
    for scenario in SCENARIOS:
        c = cohorts(a, scenario)
        for year in a.years:
            k = year - c["connect_year"]
            pairs = zip(k, c["ramp_years"], strict=True)
            ramp = pd.Series([ramp_fraction(int(n), r) for n, r in pairs],
                             index=c.index, dtype=float)
            connected = float(c.loc[k >= 0, "gw"].sum())
            ramped = float((c["gw"] * ramp).sum())
            rows.append({
                "scenario": scenario,
                "year": year,
                "connected_gw": connected,
                "ramped_gw": ramped,
                "avg_gw": ramped * a.load_factor,
                "peak_gw": ramped * a.peak_factor,
                "energy_twh": ramped * a.load_factor * _hours(year) / 1000,
            })
    return pd.DataFrame(rows).round(3)


def by_stage(a: DemandAssumptions | None = None, year: int | None = None) -> pd.DataFrame:
    """Connected GW per stage and scenario by ``year`` (default: horizon end)."""
    a = a or DemandAssumptions.from_config()
    year = year or a.end_year
    out = []
    for scenario in SCENARIOS:
        c = cohorts(a, scenario)
        g = c[c["connect_year"] <= year].groupby("stage", sort=False)["gw"].sum()
        out.append(g.rename(scenario))
    return pd.concat(out, axis=1).fillna(0.0).round(2)
