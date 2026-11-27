"""v3: can ERCOT serve load in every hour? Hourly adequacy by year, scenario and weather year.

For each future year, demand scenario, supply scenario and historical weather year:

* **Load** = the weather year's hourly ERCOT load, scaled to the 2026 level, grown to the
  future year, plus new data center load (v1) in every hour.
* **Wind, solar, hydro** = the weather year's hourly output per MW of installed capacity
  (EIA-930 / EIA-860M) x the future year's capacity (v2).
* **Firm extras**: private use networks at ERCOT's net export, plus a calibrated block of
  resources the model does not see (imports, emergency demand response, ...), fitted so the
  model reproduces ERCOT's 2019-2023 emergency record.
* **Batteries** shave the highest requirement hours each day and recharge when thermal
  plants can safely cover it.
* **Thermal plants** (gas, coal, nuclear, other) fail independently at their forced outage
  rates; a capacity outage probability table (COPT) gives the chance that available thermal
  falls short of what is left, hour by hour. Winter storms add correlated outages.

Outputs per weather year: LOLE (loss-of-load events a year, counted as days with a shortfall),
LOLH (hours), EUE (unserved energy), and the tightest hour. All assumptions:
``config/assumptions.yaml`` (``adequacy``) and docs/adequacy-assumptions.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
import pandas as pd

from gridkeepup import clean, config, demand, manual, supply
from gridkeepup.fetch import eia860m, eia930

TZ = "America/Chicago"
THERMAL = ("Gas", "Coal", "Nuclear", "Other")
SCENARIOS = ("low", "mid", "high")


# ---------------------------------------------------------------- assumptions


@dataclass(frozen=True)
class AdequacyAssumptions:
    reference_year: int
    peak_growth: float
    load_growth: dict[str, float]
    uri_rebuild: bool
    reserve_mw: float
    round_trip: float
    winter_months: tuple[int, ...]
    efor: dict[str, float]
    new_unit_mw: float
    storms: dict[str, dict]
    unmodeled_mw: float
    calibration: dict
    step_mw: int
    safe_quantile: float
    standard: float
    pun_mw: dict[str, float] = field(default_factory=dict)
    rare: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def from_config(cls, cfg: dict | None = None) -> AdequacyAssumptions:
        c = (cfg or config.assumptions())["adequacy"]
        return cls(
            int(c["reference_year"]), float(c["peak_growth_to_reference"]),
            {k: float(v) for k, v in c["non_datacenter_load_growth"].items()},
            bool(c.get("uri_rebuild", True)), float(c["reserve_mw"]),
            float(c["storage_round_trip"]), tuple(int(m) for m in c["winter_months"]),
            {k: float(v) for k, v in c["thermal_forced_outage_rate"].items()},
            float(c["new_thermal_unit_mw"]), dict(c["winter_storms"]),
            float(c["unmodeled_resources_mw"]), dict(c["calibration"]),
            int(c["copt_step_mw"]), float(c["charge_safe_quantile"]),
            float(c["reliability_standard"]),
            {"summer": manual.reference("private_use_network_summer"),
             "winter": manual.reference("private_use_network_winter")},
            dict(c.get("rare_events", {})),
        )

    def efor_for(self, technology: str) -> float:
        return self.efor.get(str(technology).strip(), self.efor["default"])



# ---------------------------------------------------------------- derived inputs


def derive_peak_growth() -> dict[str, float]:
    """Annual peak growth 2019 -> 2026, with and without large loads (inputs to the config)."""
    d = clean.clean_demand(eia930.load("demand"))
    local = d.set_index(d["timestamp_utc"].dt.tz_convert(TZ))["demand_mw"]
    p2019 = float(local[local.index.year == 2019].max())
    p2026 = manual.reference("record_peak_demand")
    ll = manual.reference("large_load_observed_peak_consumption")
    years = 2026 - 2019
    return {"peak_2019_mw": p2019, "peak_2026_mw": p2026, "large_load_2026_mw": ll,
            "with_large_loads": (p2026 / p2019) ** (1 / years) - 1,
            "without_large_loads": ((p2026 - ll) / p2019) ** (1 / years) - 1}


# ---------------------------------------------------------------- hourly weather-year profiles


def _capacity_history(op: pd.DataFrame, ret: pd.DataFrame, technologies: set[str],
                      months: pd.DatetimeIndex) -> pd.Series:
    """Installed net summer MW at the start of each month, rebuilt from unit online dates."""
    parts = []
    for df, end_prefix in ((op, None), (ret, "retirement")):
        d = df[df["technology"].isin(technologies)]
        if d.empty:
            continue
        start = pd.to_datetime({"year": pd.to_numeric(d["operating_year"]),
                                "month": pd.to_numeric(d["operating_month"]), "day": 1},
                               errors="coerce")
        if end_prefix:
            end = pd.to_datetime({"year": pd.to_numeric(d[f"{end_prefix}_year"]),
                                  "month": pd.to_numeric(d[f"{end_prefix}_month"]), "day": 1},
                                 errors="coerce")
        else:
            end = pd.Series(pd.Timestamp("2100-01-01"), index=d.index)
        parts.append(pd.DataFrame({"start": start, "end": end,
                                   "mw": pd.to_numeric(d["net_summer_capacity_mw"],
                                                       errors="coerce").fillna(0.0)}))
    u = pd.concat(parts)
    return pd.Series([u.loc[(u["start"] < m) & (u["end"] > m), "mw"].sum() for m in months],
                     index=months)


@lru_cache(maxsize=1)
def weather_profiles() -> pd.DataFrame:
    """Hourly profiles by local time: load_mw, wind_cf, solar_cf, hydro_mw, weather_year.

    Only local calendar years with complete load and generation are kept. Capacity factors are
    output / EIA-860M net summer MW installed that month, the same measure v2 projects, so
    values slightly above 1 are kept (ERCOT solar output exceeds EIA-listed MW at times).
    """
    a = AdequacyAssumptions.from_config()
    d = clean.clean_demand(eia930.load("demand")).set_index("timestamp_utc")
    g = clean.clean_generation(eia930.load("fuel_mix")).set_index("timestamp_utc")
    df = pd.DataFrame({"load_mw": d["demand_mw"]}).join(
        g[["WND", "SUN", "WAT"]].rename(columns={"WND": "wind_mw", "SUN": "solar_mw",
                                                 "WAT": "hydro_mw"}), how="inner")
    if a.uri_rebuild:
        df["load_mw"] = rebuild_uri(df["load_mw"])
    df.index = df.index.tz_convert(TZ)
    df["weather_year"] = df.index.year
    counts = df.groupby("weather_year")["load_mw"].count()
    full = {y: 8784 if pd.Timestamp(f"{y}-12-31").dayofyear == 366 else 8760
            for y in counts.index}
    keep = [y for y, n in counts.items() if n >= full[y] - 2 and
            df.loc[df["weather_year"] == y, ["load_mw", "wind_mw", "solar_mw"]].notna().all().all()]
    df = df[df["weather_year"].isin(keep)].copy()

    inv = eia860m.load_latest()
    months = pd.date_range(f"{min(keep)}-01-01", f"{max(keep)}-12-01", freq="MS")
    month_of = df.index.tz_localize(None).to_period("M").to_timestamp()
    for col, techs in (("wind", {"Onshore Wind Turbine", "Offshore Wind Turbine"}),
                       ("solar", {"Solar Photovoltaic", "Solar Thermal without Energy Storage",
                                  "Solar Thermal with Energy Storage"})):
        cap = _capacity_history(inv["operating"], inv["retired"], techs, months)
        df[f"{col}_cf"] = (df[f"{col}_mw"].clip(lower=0) / cap.reindex(month_of).to_numpy()) \
            .clip(upper=1.3)
    df["hydro_mw"] = df["hydro_mw"].clip(lower=0).fillna(0.0)
    return df[["weather_year", "load_mw", "wind_cf", "solar_cf", "hydro_mw"]]


def rebuild_uri(load: pd.Series) -> pd.Series:
    """Replace Uri load-shed hours with demand as if it had been served.

    Shape: the 24 hours before load shed began (14-15 Feb 2021), repeated; level: scaled so the
    peak equals ERCOT's estimate of demand without load shed (76,819 MW). Never lowers load.
    """
    window = clean.KNOWN_EVENTS["winter_storm_uri_load_shed"]
    start, end = (pd.Timestamp(t, tz="UTC") for t in window)
    if not ((load.index >= start) & (load.index < end)).any():
        return load
    day = load[(load.index >= start - pd.Timedelta(hours=24)) & (load.index < start)]
    if len(day) < 24:
        return load
    scale = manual.reference("uri_unconstrained_peak") / float(day.max())
    out = load.copy()
    hours = out.index[(out.index >= start) & (out.index < end)]
    shape = day.to_numpy() * scale
    rebuilt = np.array([shape[i % 24] for i in range(len(hours))])
    out.loc[hours] = np.maximum(out.loc[hours].to_numpy(), rebuilt)
    return out


# ---------------------------------------------------------------- thermal fleet and COPT


def is_chp(sector: pd.Series) -> pd.Series:
    s = sector.astype(str)
    return s.str.contains("CHP") & ~s.str.contains("Non-CHP")


def thermal_units(year: int, scenario: str, a: AdequacyAssumptions,
                  inventory: dict | None = None,
                  proj: pd.DataFrame | None = None) -> pd.DataFrame:
    """Thermal units in ``year``: today's non-CHP units not yet retired + expected additions.

    Columns: technology, fuel, summer_mw, winter_mw, efor. CHP units are dropped here and
    counted instead as ERCOT's private-use-network net export (see ``firm_mw``).
    """
    inventory = inventory or eia860m.load_latest()
    op, _ = supply.prepare(inventory)
    op = op[op["fuel"].isin(THERMAL)].copy()
    op["winter_mw"] = pd.to_numeric(op["net_winter_capacity_mw"], errors="coerce") \
        .fillna(op["mw"])
    alive = op[~(op["retire_year"] <= year)]
    units = alive[~is_chp(alive["sector"])]
    out = pd.DataFrame({"technology": units["technology"], "fuel": units["fuel"],
                        "summer_mw": units["mw"], "winter_mw": units["winter_mw"],
                        "efor": units["technology"].map(a.efor_for)})

    proj = supply.project(inventory) if proj is None else proj
    p = proj[(proj["year"] == year) & (proj["scenario"] == scenario)].set_index("fuel")
    new = []
    for fuel in THERMAL:
        added_mw = float(p["capacity_gw"].get(fuel, 0.0)) * 1000 - alive.loc[
            alive["fuel"] == fuel, "mw"].sum()
        if added_mw <= 1:
            continue
        fleet = op[op["fuel"] == fuel]
        w_ratio = fleet["winter_mw"].sum() / fleet["mw"].sum() if fleet["mw"].sum() else 1.0
        n_full, rest = divmod(added_mw, a.new_unit_mw)
        sizes = [a.new_unit_mw] * int(n_full) + ([rest] if rest > 1 else [])
        new += [{"technology": f"New {fuel}", "fuel": fuel, "summer_mw": s,
                 "winter_mw": s * w_ratio, "efor": a.efor["default"]} for s in sizes]
    return pd.concat([out, pd.DataFrame(new)], ignore_index=True) if new else \
        out.reset_index(drop=True)


@dataclass(frozen=True)
class COPT:
    """Distribution of available thermal MW (grid of ``step`` MW)."""
    step: int
    pmf: np.ndarray

    @classmethod
    def build(cls, capacities_mw: np.ndarray, efor: np.ndarray, step: int) -> COPT:
        k = np.maximum(np.rint(np.asarray(capacities_mw) / step).astype(int), 0)
        pmf = np.zeros(int(k.sum()) + 1)
        pmf[0] = 1.0
        top = 0
        for ki, q in zip(k, efor, strict=True):
            if ki == 0:
                continue
            new = pmf * q
            new[ki:top + ki + 1] += pmf[:top + 1] * (1 - q)
            pmf = new
            top += ki
        return cls(step, pmf)

    @property
    def mw(self) -> np.ndarray:
        return np.arange(len(self.pmf)) * self.step

    def mean(self) -> float:
        return float((self.pmf * self.mw).sum())

    def quantile(self, q: float) -> float:
        return float(self.mw[np.searchsorted(np.cumsum(self.pmf), q)])

    def shortfall(self, need_mw: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(P(available < need), E[max(need - available, 0)]) for each hour's need."""
        cdf = np.cumsum(self.pmf)
        partial = np.cumsum(self.pmf * self.mw)
        idx = np.ceil(np.asarray(need_mw) / self.step).astype(int) - 1   # bins strictly below
        lolp = np.where(idx < 0, 0.0, cdf[np.clip(idx, 0, len(cdf) - 1)])
        part = np.where(idx < 0, 0.0, partial[np.clip(idx, 0, len(cdf) - 1)])
        eue = np.maximum(need_mw * lolp - part, 0.0)
        return np.clip(lolp, 0.0, 1.0), eue


# ---------------------------------------------------------------- batteries


def dispatch_storage(need: np.ndarray, safe: np.ndarray, power: float, energy: float,
                     round_trip: float, lookahead: int = 24) -> tuple[np.ndarray, np.ndarray]:
    """Battery discharge and charge (MW) for each hour.

    ``need`` is what thermal plants must cover without batteries; ``safe`` is the thermal MW
    available with high confidence (a low quantile of the COPT). Batteries discharge only above
    ``safe``, shaving the highest excess hours in the next ``lookahead`` hours with the energy
    on hand (water-filling); they charge when ``safe`` covers need plus charging. Start full.
    """
    n = len(need)
    excess = np.maximum(need - safe, 0.0)
    room = np.maximum(safe - need, 0.0)
    dis = np.zeros(n)
    chg = np.zeros(n)
    soc = energy
    if power <= 0 or energy <= 0:
        return dis, chg
    for t in range(n):
        if excess[t] > 0 and soc > 0:
            window = excess[t:t + lookahead]
            capped = np.minimum(window, power)
            if capped.sum() <= soc:
                d = capped[0]
            else:                                   # water level L: sum(min(P, x - L)+) = soc
                lo, hi = 0.0, float(window.max())
                for _ in range(30):
                    mid = (lo + hi) / 2
                    if np.minimum(np.maximum(window - mid, 0.0), power).sum() > soc:
                        lo = mid
                    else:
                        hi = mid
                d = min(power, max(excess[t] - hi, 0.0))
            d = min(d, soc)
            dis[t] = d
            soc -= d
        elif room[t] > 0 and soc < energy:
            c = min(power, room[t], (energy - soc) / round_trip)
            chg[t] = c
            soc += c * round_trip
    return dis, chg


# ---------------------------------------------------------------- one run


@dataclass
class Inputs:
    """Everything that does not change with the weather year."""
    year: int
    demand_scenario: str
    supply_scenario: str
    load_factor: float          # applied to weather-year load
    datacenter_mw: float
    wind_mw: float
    solar_mw: float
    storage_mw: float
    storage_mwh: float
    copt: dict[str, COPT]       # 'summer' / 'winter'
    expected_outage_mw: dict[str, float]


def build_inputs(year: int, demand_scenario: str, supply_scenario: str,
                 a: AdequacyAssumptions | None = None, cache: dict | None = None) -> Inputs:
    a = a or AdequacyAssumptions.from_config()
    cache = {} if cache is None else cache
    if "proj" not in cache:
        cache["inventory"] = eia860m.load_latest()
        cache["proj"] = supply.project(cache["inventory"])
        cache["demand"] = demand.project()
    proj, dem = cache["proj"], cache["demand"]
    p = proj[(proj["year"] == year) & (proj["scenario"] == supply_scenario)].set_index("fuel")
    dc = dem[(dem["year"] == year) & (dem["scenario"] == demand_scenario)]
    key = ("copt", year, supply_scenario)
    if key not in cache:
        units = thermal_units(year, supply_scenario, a, cache["inventory"], proj)
        cache[key] = {s: COPT.build(units[f"{s}_mw"].to_numpy(), units["efor"].to_numpy(),
                                    a.step_mw) for s in ("summer", "winter")}
        cache[key + ("outage",)] = {s: float((units[f"{s}_mw"] * units["efor"]).sum())
                                    for s in ("summer", "winter")}
    factor = (1 + a.load_growth[demand_scenario]) ** (
        year - a.reference_year)
    return Inputs(year, demand_scenario, supply_scenario, factor,
                  float(dc["peak_gw"].iloc[0]) * 1000 if len(dc) else 0.0,
                  float(p["capacity_gw"].get("Wind", 0)) * 1000,
                  float(p["capacity_gw"].get("Solar", 0)) * 1000,
                  float(p["capacity_gw"].get("Storage", 0)) * 1000,
                  float(p["storage_gwh"].get("Storage", 0)) * 1000,
                  cache[key], cache[key + ("outage",)])


def storm_extra_mw(index: pd.DatetimeIndex, expected_outage_mw: float,
                   a: AdequacyAssumptions) -> np.ndarray:
    """Extra correlated thermal outage during winter storm windows (beyond normal outages)."""
    extra = np.zeros(len(index))
    for s in a.storms.values():
        start = pd.Timestamp(s["start"], tz="UTC")
        end = pd.Timestamp(s["end"], tz="UTC")
        hit = (index >= start) & (index < end)
        extra[hit] = max(float(s["thermal_out_mw"]) - expected_outage_mw, 0.0)
    return extra


def hourly_need(prof: pd.DataFrame, x: Inputs, a: AdequacyAssumptions,
                extra_load_mw: float = 0.0) -> pd.DataFrame:
    """What thermal + batteries must cover each hour (load + reserve - variable and firm)."""
    w = prof["weather_year"].to_numpy()
    winter = np.isin(prof.index.month, a.winter_months)
    load = (prof["load_mw"].to_numpy() * (1 + a.peak_growth) ** (a.reference_year - w)
            * x.load_factor + x.datacenter_mw + extra_load_mw)
    renew = (prof["wind_cf"].to_numpy() * x.wind_mw + prof["solar_cf"].to_numpy() * x.solar_mw
             + prof["hydro_mw"].to_numpy())
    pun = np.where(winter, a.pun_mw["winter"], a.pun_mw["summer"])
    storm = np.where(winter, storm_extra_mw(prof.index, x.expected_outage_mw["winter"], a), 0.0)
    need = load + a.reserve_mw - renew - pun - a.unmodeled_mw + storm
    return pd.DataFrame({"load_mw": load, "renewables_mw": renew, "need_mw": need,
                         "winter": winter}, index=prof.index)


def run_weather_year(prof: pd.DataFrame, x: Inputs, a: AdequacyAssumptions,
                     extra_load_mw: float = 0.0, detail: bool = False):
    h = hourly_need(prof, x, a, extra_load_mw)
    need = h["need_mw"].to_numpy()
    winter = h["winter"].to_numpy()
    safe = np.where(winter, x.copt["winter"].quantile(a.safe_quantile),
                    x.copt["summer"].quantile(a.safe_quantile))
    dis, chg = dispatch_storage(need, safe, x.storage_mw, x.storage_mwh, a.round_trip)
    after = need - dis + chg
    lolp = np.zeros(len(after))
    eue = np.zeros(len(after))
    for season, mask in (("winter", winter), ("summer", ~winter)):
        lolp[mask], eue[mask] = x.copt[season].shortfall(after[mask])
    mean_avail = np.where(winter, x.copt["winter"].mean(), x.copt["summer"].mean())
    margin = mean_avail - after
    idx = h.index
    rare_mask = np.zeros(len(idx), dtype=bool)
    summary: dict = {}
    for name, ev in a.rare.items():
        m = (idx >= pd.Timestamp(ev["start"], tz="UTC")) & (idx < pd.Timestamp(ev["end"], tz="UTC"))
        rare_mask |= m
        summary |= _metrics(lolp, eue, idx, m, prefix=f"rare_{name}_")
    summary |= _metrics(lolp, eue, idx, ~rare_mask, prefix="")
    summary["winter_lole"] = _metrics(lolp, eue, idx, ~rare_mask & winter, prefix="")["lole"]
    normal = np.where(rare_mask, np.inf, margin)
    t = int(np.argmin(normal))
    summary |= {"worst_lolp": float(lolp[~rare_mask].max()) if (~rare_mask).any() else 0.0,
                "tightest_hour": idx[t], "tightest_margin_mw": float(margin[t]),
                "tightest_load_mw": float(h["load_mw"].iloc[t])}
    if detail:
        h = h.assign(discharge_mw=dis, charge_mw=chg, lolp=lolp, eue_mw=eue, margin_mw=margin,
                     rare=rare_mask)
        return summary, h
    return summary


def _metrics(lolp: np.ndarray, eue: np.ndarray, idx: pd.DatetimeIndex, mask: np.ndarray,
             prefix: str) -> dict:
    """LOLE (days with a shortfall, summed daily-max LOLP), LOLH and EUE over ``mask`` hours."""
    if not mask.any():
        return {f"{prefix}lole": 0.0, f"{prefix}lolh": 0.0, f"{prefix}eue_gwh": 0.0}
    daily = pd.Series(lolp[mask], index=idx[mask]).groupby(idx[mask].normalize()).max()
    return {f"{prefix}lole": float(daily.sum()), f"{prefix}lolh": float(lolp[mask].sum()),
            f"{prefix}eue_gwh": float(eue[mask].sum()) / 1000}


def run(years=None, demand_scenarios=SCENARIOS, supply_scenarios=SCENARIOS,
        a: AdequacyAssumptions | None = None, cache: dict | None = None) -> pd.DataFrame:
    """One row per year x demand scenario x supply scenario x weather year."""
    a = a or AdequacyAssumptions.from_config()
    cache = {} if cache is None else cache
    prof = weather_profiles()
    years = years or list(range(a.reference_year, config.assumptions()["horizon"]["end_year"] + 1))
    rows = []
    for year in years:
        for ds in demand_scenarios:
            for ss in supply_scenarios:
                x = build_inputs(year, ds, ss, a, cache)
                for wy, p in prof.groupby("weather_year"):
                    rows.append({"year": year, "demand": ds, "supply": ss, "weather_year": wy,
                                 **run_weather_year(p, x, a)})
    return pd.DataFrame(rows)


def expected(results: pd.DataFrame, a: AdequacyAssumptions | None = None) -> pd.Series:
    """Expected annual LOLE / LOLH / EUE for one set of weather-year rows.

    Ordinary hours: equal weight per weather year. Rare events (Uri): their own outcome x their
    annual probability, instead of 1 / number of weather years.
    """
    a = a or AdequacyAssumptions.from_config()
    out = {m: results[m].mean() for m in ("lole", "lolh", "eue_gwh", "winter_lole")
           if m in results}
    for name, ev in a.rare.items():
        if f"rare_{name}_lole" in results and "winter_lole" in out:   # rare events are winter
            rare_lole = results[f"rare_{name}_lole"].sum()
            out["winter_lole"] += float(ev["annual_probability"]) * rare_lole
        for m in ("lole", "lolh", "eue_gwh"):
            col = f"rare_{name}_{m}"
            if col in results:
                out[m] += float(ev["annual_probability"]) * results[col].sum()
    return pd.Series(out)


def summarize(results: pd.DataFrame, a: AdequacyAssumptions | None = None) -> pd.DataFrame:
    """Expected LOLE, LOLH, EUE per year x scenario pair, plus the worst ordinary weather year."""
    a = a or AdequacyAssumptions.from_config()
    keys = ["year", "demand", "supply"]
    rows = []
    for k, g in results.groupby(keys):
        worst = g.loc[g["lole"].idxmax()]
        rare = {f"{name}_week_eue_gwh": g[f"rare_{name}_eue_gwh"].sum()
                for name in a.rare if f"rare_{name}_eue_gwh" in g}
        e = expected(g, a).to_dict()
        e["winter_share"] = e.pop("winter_lole", 0.0) / e["lole"] if e["lole"] else 0.0
        rows.append({**dict(zip(keys, k, strict=True)), **e,
                     "worst_weather_year": int(worst["weather_year"]),
                     "worst_weather_lole": float(worst["lole"]),
                     "tightest_margin_mw": float(g["tightest_margin_mw"].min()), **rare})
    return pd.DataFrame(rows)


def headroom(year: int, demand_scenario: str = "mid", supply_scenario: str = "mid",
             a: AdequacyAssumptions | None = None, cache: dict | None = None,
             lo: float = -40000.0, hi: float = 60000.0, tol_mw: float = 250.0) -> float:
    """Extra flat load (MW) that brings average LOLE to the reliability standard.

    Positive: room for that much more round-the-clock load (e.g. data centers). Negative: that
    much load would have to come off in risky hours to meet the standard.
    """
    a = a or AdequacyAssumptions.from_config()
    cache = {} if cache is None else cache
    prof = weather_profiles()
    x = build_inputs(year, demand_scenario, supply_scenario, a, cache)
    groups = [p for _, p in prof.groupby("weather_year")]

    def lole(extra: float) -> float:
        rows = pd.DataFrame([run_weather_year(p, x, a, extra) for p in groups])
        return float(expected(rows, a)["lole"])

    if lole(lo) > a.standard:
        return lo
    if lole(hi) <= a.standard:
        return hi
    while hi - lo > tol_mw:
        mid = (lo + hi) / 2
        if lole(mid) > a.standard:
            hi = mid
        else:
            lo = mid
    return lo


@lru_cache(maxsize=16)
def _backtest_inputs(year: int) -> Inputs:
    """The fleet as of 1 July of ``year``, rebuilt from EIA-860M online and retirement dates."""
    a = AdequacyAssumptions.from_config()
    inv = eia860m.load_latest()
    when = pd.Timestamp(f"{year}-07-01")

    def alive(df: pd.DataFrame, end_prefix: str | None) -> pd.DataFrame:
        start = pd.to_datetime({"year": pd.to_numeric(df["operating_year"]),
                                "month": pd.to_numeric(df["operating_month"]), "day": 1},
                               errors="coerce")
        ok = start < when
        if end_prefix:
            end = pd.to_datetime({"year": pd.to_numeric(df[f"{end_prefix}_year"]),
                                  "month": pd.to_numeric(df[f"{end_prefix}_month"]), "day": 1},
                                 errors="coerce")
            ok &= end > when
        return df[ok]

    fleet = pd.concat([alive(inv["operating"], None), alive(inv["retired"], "retirement")],
                      ignore_index=True)
    fleet["fuel"] = fleet["technology"].map(supply.fuel_group)
    num = {c: pd.to_numeric(fleet[c], errors="coerce").fillna(0.0)
           for c in ("net_summer_capacity_mw", "net_winter_capacity_mw",
                     "nameplate_energy_capacity_mwh")}
    th = fleet[fleet["fuel"].isin(THERMAL) & ~is_chp(fleet["sector"])]
    efor = th["technology"].map(a.efor_for).to_numpy()
    copt = {"summer": COPT.build(num["net_summer_capacity_mw"][th.index].to_numpy(), efor,
                                 a.step_mw),
            "winter": COPT.build(num["net_winter_capacity_mw"][th.index].to_numpy(), efor,
                                 a.step_mw)}
    by_fuel = num["net_summer_capacity_mw"].groupby(fleet["fuel"]).sum()
    sto = fleet["fuel"] == "Storage"
    x = Inputs(year, "actual", "actual", 1.0, 0.0, float(by_fuel.get("Wind", 0)),
               float(by_fuel.get("Solar", 0)), float(by_fuel.get("Storage", 0)),
               float(num["nameplate_energy_capacity_mwh"][sto].sum()), copt,
               {k: float((num[f"net_{k}_capacity_mw"][th.index] * efor).sum())
                for k in ("summer", "winter")})
    return x


def backtest(year: int = 2023, a: AdequacyAssumptions | None = None,
             reserve_mw: float | None = None, unmodeled_mw: float | None = None) -> dict:
    """Run the model on ``year`` as it was: actual load, that year's fleet, no growth.

    Fleet rebuilt from EIA-860M online and retirement dates (thermal non-CHP, wind, solar,
    batteries) as of 1 July of ``year``; private use networks as in the base case.
    """
    a = a or AdequacyAssumptions.from_config()
    prof = weather_profiles()
    p = prof[prof["weather_year"] == year]
    x = _backtest_inputs(year)
    copt = x.copt
    b = AdequacyAssumptions(**{
        **a.__dict__, "peak_growth": 0.0, "reference_year": year,
        "reserve_mw": a.reserve_mw if reserve_mw is None else reserve_mw,
        "unmodeled_mw": a.unmodeled_mw if unmodeled_mw is None else unmodeled_mw})
    summary, h = run_weather_year(p, x, b, detail=True)
    risky = h[h["lolp"] > 0.01]
    return {"year": year, "thermal_gw": round(copt["summer"].mean() / 1000, 1),
            "wind_gw": round(x.wind_mw / 1000, 1), "solar_gw": round(x.solar_mw / 1000, 1),
            "storage_gw": round(x.storage_mw / 1000, 1), **summary,
            "risky_days": sorted({str(d.date()) for d in risky.index})}


def calibrate(a: AdequacyAssumptions | None = None, tol_mw: float = 50.0) -> dict:
    """Unmodeled MW that makes expected emergency days over the calibration years match history.

    Emergency day = a day when available supply falls below load + the EEA reserve threshold of
    the time (2,300 MW). Uri week excluded (rare event). Returns the fitted MW and the check.
    """
    a = a or AdequacyAssumptions.from_config()
    c = a.calibration
    years = [y for y in c["years"] if y in set(weather_profiles()["weather_year"])]

    def days(u: float) -> float:
        return sum(backtest(y, a, float(c["eea_reserve_mw"]), u)["lole"] for y in years)

    lo, hi = 0.0, 20000.0
    while hi - lo > tol_mw:
        mid = (lo + hi) / 2
        if days(mid) > float(c["eea_days"]):
            lo = mid
        else:
            hi = mid
    fitted = round(hi / 50) * 50
    by_year = {y: round(backtest(y, a, float(c["eea_reserve_mw"]), fitted)["lole"], 2)
               for y in years}
    return {"unmodeled_mw": fitted, "years": years, "target_days": c["eea_days"],
            "model_days_by_year": by_year, "model_days_uncalibrated": round(days(0.0), 1)}



def write_results(headroom_pairs=(("mid", "low"), ("mid", "mid"), ("mid", "high"),
                                  ("low", "mid"), ("high", "mid"))) -> dict[str, pd.DataFrame]:
    """Run everything and save small result tables to data/derived/ (committed, so charts and
    the dashboard need no raw data)."""
    from gridkeepup.paths import DERIVED_DIR
    a = AdequacyAssumptions.from_config()
    cache: dict = {}
    by_wy = run(a=a, cache=cache)
    summary = summarize(by_wy, a)
    years = sorted(summary["year"].unique())
    room = pd.DataFrame([{"year": y, "demand": d, "supply": s,
                          "headroom_gw": headroom(y, d, s, a, cache) / 1000}
                         for d, s in headroom_pairs for y in years])
    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    out = {"adequacy_by_weather_year": by_wy.assign(
               tightest_hour=by_wy["tightest_hour"].astype(str)),
           "adequacy_summary": summary, "adequacy_headroom": room}
    for name, df in out.items():
        df.round(4).to_csv(DERIVED_DIR / f"{name}.csv", index=False)
    return out


def load_results(name: str) -> pd.DataFrame:
    from gridkeepup.paths import DERIVED_DIR
    path = DERIVED_DIR / f"{name}.csv"
    return pd.read_csv(path) if path.exists() else pd.DataFrame()
