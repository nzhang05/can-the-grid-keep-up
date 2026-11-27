# Hourly adequacy (v3)

Status: **proposed 2026-11-27**, for review. Values live in
[`config/assumptions.yaml`](../config/assumptions.yaml) under `adequacy`; every assumption is
in the [register](assumptions.md) (section H). Values computed from data are recomputed by
`uv run gridkeepup derive` ([derived-values.md](derived-values.md)). Run
`uv run gridkeepup adequacy`; results are saved to `data/derived/adequacy_*.csv`.

## The question

v1 says how much load data centers add; v2 says how much generation gets built. Neither says
whether the lights stay on at 9 pm on a still August evening, or at 8 am in an ice storm.
v3 replays every hour of real weather on each future year's grid and asks: how often would
ERCOT have to rotate outages?

## Result

Expected loss-of-load events per year (an event = a day ERCOT would have to shed firm load).
Texas's standard is **0.1**: one event in ten years.

| Demand | Supply | 2026 | 2027 | 2028 | 2029 | 2030 |
| --- | --- | --- | --- | --- | --- | --- |
| Mid | Mid | 0.18 | **0.39** | 0.18 | 0.22 | 0.15 |
| Mid | Low | 0.21 | 0.74 | 0.66 | 0.72 | 0.72 |
| Mid | High | 0.18 | 0.31 | 0.12 | 0.12 | 0.09 |
| Low | Mid | 0.18 | 0.22 | 0.08 | 0.08 | 0.06 |
| High | Mid | 0.19 | 0.65 | 0.84 | 1.75 | 4.87 |

Round-the-clock load the grid could add (+) or would have to shed in risky hours (-) to meet
the standard, GW:

| Demand | Supply | 2026 | 2027 | 2028 | 2029 | 2030 |
| --- | --- | --- | --- | --- | --- | --- |
| Mid | Mid | -2.1 | -3.9 | -2.1 | -3.5 | -3.1 |
| Mid | Low | -2.3 | -5.6 | -5.0 | -5.6 | -6.2 |
| Mid | High | -1.9 | -3.3 | -0.9 | -1.5 | +0.6 |
| Low | Mid | -1.9 | -2.5 | +1.0 | +2.0 | +5.3 |
| High | Mid | -2.1 | -5.2 | -6.2 | -11.9 | -16.8 |

What it says:

- **The mid case misses the standard every year, but not by much**: 2-4 GW of load would need
  to be flexible in the riskiest hours. That is v4's question.
- **2027 is the tightest year.** Data center load ramps up before the 2028-2030 wave of solar
  and batteries arrives.
- **Winter is the risk.** 77-90% of mid-case risk is in December-February: an Elliott-like
  storm (cold, high morning load, frozen plants, weak wind, batteries drained overnight) and a
  Uri-like storm. Summer evenings, the old worry, are mostly covered by batteries in this model.
- **A Uri-like week** would still mean about 250-340 GWh of unserved energy in the mid case
  (weighted at a 2% chance a year).
- **High demand outruns supply.** If data centers connect at the high-case pace, the shortfall
  reaches 17 GW of load to shed in risky hours by 2030 even with mid supply.
- ERCOT's own trial reliability assessment for 2026 also found the standard is not met: its
  consultant estimated 15 GW of perfect capacity needed in 2026, with a much higher load
  forecast than this model's.
  [ERCOT SAWG, Feb 2026](https://www.ercot.com/files/docs/2026/01/30/15.-260204-SAWG-presentation-to-WMS-v1.pdf)

## How it works

For each year, scenario pair and weather year (2019-2023), hour by hour:

1. **Load** = that hour's real ERCOT load (EIA-930), scaled to the 2026 level (+2.9% a year,
   ERCOT's peak growth 2019-2026), grown at 1.2 / 2.2 / 3.2% a year to the future year, plus
   new data center load from v1 at its peak value in every hour.
2. **Wind and solar** = that hour's real output per MW installed at the time, times v2's
   capacity for the year. Hydro as it was.
3. **Firm extras**: private use networks at ERCOT's net export (3.2 GW summer, 4.3 GW winter)
   and 5.6 GW of calibrated unmodeled resources (below).
4. **Batteries** shave the tightest hours of the next day with the energy on hand and recharge
   when thermal plants can cover it safely.
5. **Thermal plants** (gas, coal, nuclear) fail at random at their forced outage rates; a
   capacity outage table gives the exact chance that what is left is not enough. Winter storms
   add correlated outages.
6. A shortfall is when load plus 1,500 MW of reserves exceeds supply (ERCOT's point for rotating
   outages).

## Calibration: the model first saw far too much risk

Run on 2019-2023 as they actually happened (each year's real load and fleet), the uncalibrated
model expected **74 emergency days**. ERCOT declared **3** (EEA1 twice in August 2019, EEA2 on
6 September 2023), with no rotating outages outside Uri. The model misses resources that show
up in tight hours: imports over DC ties, emergency demand response and load resources,
conservation appeals, and plants that fail less at peak than their annual averages.

Rather than guess each one, the model adds one block of firm supply, **5.6 GW**, fitted so its
expected emergency days in 2019-2023 equal 3. Model days by year with it: 2019 0.68, 2020 0.31,
2021 0.02, 2022 0.37, 2023 1.61, so it also puts the risk in the right years (2023 and 2019).
It is held constant to 2030. This is the single most important number in v3: without it every
year fails badly; with more of it, every year passes.

## Key inputs

| Input | Value | Source |
| --- | --- | --- |
| Reliability standard | 0.1 loss-of-load events a year | PUCT, 16 TAC 25.508 |
| Reserve at which firm load is shed | 1,500 MW | ERCOT EEA3 procedure |
| Forced outage rates | combined cycle 5.7%, coal 14.1%, other 9.2%, nuclear 3% (judgment) | NERC 2026 State of Reliability |
| Winter storm thermal outages | Elliott 14 GW, Heather 7 GW; Uri at Elliott's level | CSIS citing GridStatus.io |
| Uri demand if served | 76,819 MW peak | ERCOT estimate |
| Uri-like storm chance | 2% a year | Texas state climatologist |
| Battery round trip | 82% | EIA (2019 fleet) |
| Private use network net export | 3,194 MW summer, 4,283 MW winter | ERCOT CDR May 2025 |

## What this does not cover

- Transmission limits inside ERCOT, and gas supply problems beyond the storm outages.
- PUCT's duration and magnitude criteria (only frequency is tested).
- Data centers that can curtail (SB 6 lets ERCOT curtail new large loads in emergencies),
  on-site generation, and other flexibility: **v4**.
- Weather years 2024 and 2025 (they need 2025 demand data; 2024 includes Winter Storm Heather).
- Only five weather years: rare heat and cold beyond them is represented only by the Uri week.
