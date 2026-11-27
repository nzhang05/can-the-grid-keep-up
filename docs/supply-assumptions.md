# Supply assumptions (v2)

Status: **decided 2026-11-27**, including the timing of ERCOT queue projects (time-based
completion curves, see "Queue timing" below). Values live in
[`config/assumptions.yaml`](../config/assumptions.yaml) under `supply`; every assumption is in
the [register](assumptions.md) (section F). Values computed from data are recomputed by
`uv run gridkeepup derive`, which writes inputs and arithmetic to
[derived-values.md](derived-values.md). Run `uv run gridkeepup supply`.

## The question

How much generation and storage will ERCOT have each year to 2030, by fuel?

## Current result (EIA-860M to 2027, ERCOT queue from 2028)

Total installed capacity, net summer GW (expected values):

| Year | Low | Mid | High |
| --- | --- | --- | --- |
| Today (Oct 2026) | 176.5 | 176.5 | 176.5 |
| 2026 (year end) | 185.0 | 188.9 | 189.2 |
| 2027 | 188.8 | 198.7 | 204.2 |
| 2028 | 205.2 | 225.8 | 242.4 |
| 2029 | 222.0 | 254.5 | 292.8 |
| 2030 | 234.8 | 279.8 | 337.3 |

Mid case by fuel, GW (year end):

| Fuel | 2026 | 2028 | 2030 |
| --- | --- | --- | --- |
| Gas | 62.2 | 67.3 | 75.0 |
| Wind | 41.7 | 45.5 | 50.0 |
| Solar | 42.7 | 55.5 | 66.9 |
| Batteries | 22.0 | 37.8 | 68.0 |
| Coal | 13.7 | 13.1 | 13.1 |
| Nuclear | 5.0 | 5.0 | 5.0 |

The 2026 jump is the 9.4 GW already built and awaiting commercial operation.

### How plausible is this?

Mid-case additions are 27-29 GW a year in 2028-2030, against ERCOT's record of 15.3 GW
(2025); the low case (13-17 GW a year) is close to the record pace. Three checks:

- **The timing method is not what makes it high.** Replayed on ERCOT's queue as it stood at
  the end of 2019, 2020 and 2021, the same method predicted 17-22 GW over the next four years;
  ERCOT actually added 23-35 GW from those queues (actual / model 1.35-1.77). If anything it
  runs low. Numbers in [derived-values.md](derived-values.md).
- **The queue is what makes it high.** ERCOT's queue is about twice the size it was in 2021
  (446 GW in the October 2026 GIS report, 162 GW at end-2021). The model assumes today's
  projects complete at historical rates; it does not assume a limit on how much ERCOT can
  connect or developers can build in a year. That limit is unknown and is the largest
  uncertainty in v2.
- **Batteries are the swing.** Mid case reaches 55 GW of batteries by 2029. Modo Energy's
  outlook for ERCOT is 40-55 GW operational by 2029, depending on attrition, so mid sits at
  the top of their range. [Modo Energy, Feb 2026](https://modoenergy.com/research/en/ercot-battery-buildout-2025-annual-report)

These are installed GW. Solar and batteries count for much less in the tightest evening
hours; v3 tests that hour by hour.

## Queue timing (decided)

Eventual completion odds applied at each project's projected online date put 44 GW of
additions in 2028 alone, three times ERCOT's record. ERCOT's history shows completion spreads
over several years after an agreement. So, for each queue project with a signed agreement or
in study:

1. **Curve (shape).** From ERCOT history (LBNL), the share of capacity online within k years
   of signing an agreement (signed projects) or entering the queue (study-only projects), by
   fuel, k = 0 to 12. Only cohorts with k full years of follow-up count, capacity-weighted,
   made non-decreasing; a year with under 0.5 GW of sample repeats the previous year.
   Fuels other than wind, gas, solar and batteries use the all-fuel curve. Written by
   `gridkeepup derive` to [`data/derived/completion_curves.csv`](../data/derived/completion_curves.csv)
   (committed; a test checks it against the data).
2. **Level.** The curve is rescaled so its plateau equals the stage's eventual odds (table 3).
3. **Age, conditional.** A project that signed in 2023 is 3 years in at the 2026 snapshot and
   not online yet; its chance of being online by year Y is
   (G(3 + Y - 2026) - G(3)) / (1 - G(3)), where G is the rescaled curve.
4. **Never before its projected date.** The chance is 0 before the project's projected
   online year; capacity that would have arrived earlier arrives in that year.

Share online within k years of signing (curve before rescaling):

| Fuel | 1 year | 2 years | 3 years | 4 years |
| --- | --- | --- | --- | --- |
| Gas | 2% | 24% | 38% | 39% |
| Solar | 1% | 12% | 34% | 47% |
| Batteries | 1% | 3% | 16% | 75% |
| Wind | 2% | 24% | 42% | 49% |

Thin sample: the battery curve from year 4 on rests on 0.7 GW of agreements or less (the
battery boom is recent). Full table with sample sizes in [derived-values.md](derived-values.md).

### Tax-credit cliff for wind and solar

Federal tax credits end for wind and solar projects that start construction after 4 July 2026
and enter service after 2027 (the 2025 budget law, OBBBA). Projects that started construction
in time keep them. Batteries and gas are not affected. ERCOT's history has no such break, and
the GIS report does not show which projects started construction for tax purposes (ERCOT notes
construction dates are not yet fully reported). So queue wind and solar not yet under
construction (signed or study) get their odds multiplied by a bracket:
**low 0 (none proceed), mid 0.5 (half), high 1 (all, as if history still applied).** This is a
judgment bracket, not derived. Effect on mid 2030: -21.5 GW (solar -14.9, wind -6.6).
[Kirkland & Ellis, Aug 2025](https://www.kirkland.com/publications/kirkland-alert/2025/08/one-big-beautiful-bill-act-brings-big-changes-to-green-energy-tax-credits)

## Evidence

### ERCOT completion rates (computed from LBNL Queued Up, data through 2025)

Share of capacity by status at end-2025, for ERCOT projects that signed an interconnection
agreement (IA) in 2000-2022:

| Fuel | Operating | Still in progress | Withdrawn | Sample |
| --- | --- | --- | --- | --- |
| Wind | 69% | 11% | 20% | 46.8 GW |
| Gas | 54% | 3% | 43% | 27.8 GW |
| Solar | 50% | 33% | 17% | 38.5 GW |
| Batteries | 42% | 48% | 10% | 4.1 GW |
| All ERCOT | 56% | 17% | 27% | 149.1 GW |

Of all ERCOT requests submitted 2000-2020, 24% of capacity is operating, 15% still in
progress and 61% withdrawn. Median time from signed agreement to operation: gas 1.8 years,
wind 2.2, solar 2.5, batteries 3.3. Completed projects came online close to their last
reported date (median difference about 0), so reported dates are reasonable once a project
is far along.

Two readings: **gas withdraws often** after signing (43%), and **batteries rarely withdraw**
(10%) but take longest, so their 42% completion is a floor, not a forecast.

Method: `03. Complete Queue Data`, `region == "ERCOT"`, capacity-weighted on `mw_1`, suspended
counted as withdrawn. Reproduced by `src/gridkeepup/lbnl.py`; `gridkeepup derive` prints it.

### National context

- Near-term plans mostly happen: 78% of capacity planned for the next year came online on
  schedule (EIA, 2017 cohort); 2024 solar: 36 GW planned, 31 GW installed.
  [EIA 2018](https://www.eia.gov/todayinenergy/detail.php?id=36513),
  [EIA 2025](https://www.eia.gov/todayinenergy/detail.php?id=66604)
- Delays are common but short (about 20% of planned solar reports one, mostly 1-2 months);
  cancellations are under 1% a month. [EIA 2025](https://www.eia.gov/todayinenergy/detail.php?id=66604)
- Nationally only 13% of 2000-2020 requested capacity reached operation; ERCOT is the best
  region. [LBNL Queued Up 2026](https://emp.lbl.gov/publications/queued-2026-edition-characteristics)

### ERCOT's pipeline (October 2026)

- **EIA-860M planned (ERCOT):** 9.4 GW built and awaiting commercial operation, 18.3 GW under
  construction, 5.9 GW approved, 14.9 GW in approvals, 37.2 GW not yet in approvals.
- **ERCOT GIS report (large generators, 446 GW):** 19.4 GW synchronized, 1.2 GW energized,
  10.2 GW in construction, 114.7 GW with a signed IA, 300.4 GW in study only. Projects with a
  signed IA and a projected online date in 2028-2030: 78.8 GW (mostly solar and batteries).
  ERCOT's "OTH" fuel code is batteries (828 of 832 projects).

## Proposed values

### 1. EIA-860M planned projects (implemented)

Chance a planned unit reaches operation, by EIA status:

| Status | Meaning | Low | Mid | High | Delay added (low / mid / high) | Basis |
| --- | --- | --- | --- | --- | --- | --- |
| TS | Built, awaiting commercial operation | 98% | 99% | 100% | 0 / 0 / 0 | Physically complete |
| V | Under construction, more than 50% | 90% | 95% | 100% | 1 / 0 / 0 | EIA on-schedule history |
| U | Under construction, 50% or less | 80% | 90% | 95% | 1 / 0 / 0 | EIA on-schedule history |
| T | Approvals received | 45% | **56%** | 70% | 1 / 1 / 0 | ERCOT post-IA completion (was 65%) |
| L | Approvals pending | 30% | 40% | 55% | 2 / 1 / 0 | Between T and P (was 45%) |
| P | Planned, no approvals | 15% | **24%** | 35% | 2 / 1 / 1 | ERCOT request completion (was 25%) |

### 2. Source split by year (decided)

EIA and ERCOT list many of the same projects under different names: matching by name and
county links only about 10% of them, so the lists cannot simply be merged. Proposal:

| Part | Source |
| --- | --- |
| Today's fleet and announced retirements | EIA-860M |
| New projects with a planned online year up to 2027 | EIA-860M planned (table 1) |
| New projects with a projected online date from 2028 | ERCOT GIS report (table 3), replacing EIA's 2028+ entries |

Measured risk: name and county matching finds 18 projects (3.5 GW nameplate) that EIA lists
for 2026-2027 and ERCOT lists for 2028, which would count twice. Small next to the pipeline;
recorded in the register (F17).

### 3. ERCOT GIS projects from 2028 (decided)

Stage from the report's milestone dates. Eventual odds for signed and study-only projects come
straight from ERCOT's history with one rule: **low = share already operating, mid = operating
+ half of still-in-progress, high = operating + all still-in-progress.** Signed uses projects
with agreements signed 2000-2022; study uses all requests submitted 2000-2020.

| Stage | Wind | Gas | Solar | Batteries | Timing |
| --- | --- | --- | --- | --- | --- |
| Synchronized / energized | 98 / 99 / 100% | same | same | same | Projected date |
| Construction started | 80 / 90 / 95% | same | same | same | Projected date, +1 / 0 / 0 years |
| Agreement signed | 69 / 74 / 80% | 54 / 56 / 57% | 50 / 67 / 83% | 42 / 66 / 90% | Curves (above) |
| Study only | 28 / 31 / 34% | 27 / 29 / 32% | 23 / 34 / 46% | 13 / 39 / 66% | Curves (above) |

Other fuels in the queue (nuclear, hydro, other) use the all-ERCOT rates: signed 56 / 64 / 73%,
study 24 / 32 / 39%. Wind and solar signed and study odds are then multiplied by the
tax-credit bracket (0 / 0.5 / 1). Study-only odds replace the earlier 10 / 20 / 30%
placeholder: timing is now handled by the curves, so the level is the eventual rate.

Capacity conversion: ERCOT reports nameplate MW. Each fuel's ratio is net summer MW / nameplate
MW of today's operating fleet (EIA-860M): gas 62,175 / 69,930 = 0.89; solar 1.00; wind 1.00;
batteries 0.99.

### 4. Other

- Planned batteries: 1.7 hours of storage. Derived: EIA-860M has no MWh for planned batteries,
  so they get today's ERCOT fleet average: 33,021 MWh / 19,605 MW nameplate across 270
  operating batteries = 1.68, rounded to 1.7 hours.
- Retirements: only announced dates (about 1.4 GW by 2030).
- Fermi America's 4.5 GW of planned nuclear (Carson County) is for 2031-2032, after the horizon.

## What this does not cover

- Behind-the-meter generation at data centers (decided in v3).
- Accredited capacity: how much each fuel delivers in the tightest hours. That is what the
  hourly model in v3 tests; installed GW overstates solar and wind at evening peaks.
- Gas turbine supply limits and wind permitting headwinds beyond what ERCOT's history shows.

## Decisions (2026-11-27)

- [x] EIA status odds (table 1), including the ERCOT-based changes to T, L and P
- [x] Delays as proposed
- [x] Source split by year: EIA to 2027, ERCOT GIS from 2028 (table 2)
- [x] ERCOT GIS stage odds and the low / mid / high rule (table 3)
- [x] 1.7-hour duration for planned batteries, nameplate-to-summer conversion for ERCOT MW;
  every derived value states its inputs and arithmetic (derived-values.md)
- [x] Queue timing: time-based completion curves from ERCOT history; study-only odds derived
  by fuel; queue switched on
- [x] Tax-credit bracket for queue wind and solar not yet under construction (0 / 0.5 / 1)
