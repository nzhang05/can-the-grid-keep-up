# Supply assumptions (v2): proposal for review

Status: **proposed, pending review.** Updated 2026-11-26 with ERCOT-specific completion
rates computed from LBNL's project-level queue data and ERCOT's October 2026 interconnection
report. Values live in [`config/assumptions.yaml`](../config/assumptions.yaml) under `supply`;
every assumption is also in the [register](assumptions.md) (section F).
Run `uv run gridkeepup supply`.

## The question

How much generation and storage will ERCOT have each year to 2030, by fuel?

## Current result (EIA-860M only, ERCOT-based odds)

Total installed capacity, net summer GW (expected values):

| Year | Low | Mid | High |
| --- | --- | --- | --- |
| Today (Oct 2026) | 176.5 | 176.5 | 176.5 |
| 2026 (year end) | 185.0 | 188.9 | 189.2 |
| 2028 | 198.1 | 205.3 | 214.7 |
| 2030 | 208.6 | 215.4 | 222.0 |

Mid case 2030 vs today: solar +22.1 GW, storage +10.9 GW (52 GWh), gas +3.7, wind +2.6,
coal -0.6, nuclear flat. The 2026 jump is the 9.4 GW already built and awaiting commercial
operation.

**2029-2030 is understated** because most projects for those years are not reported to EIA
yet. The proposed fix below (ERCOT's interconnection report from 2028) is not implemented
yet; it waits for your decision.

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

Method: `03. Complete Queue Data`, `region == "ERCOT"`, capacity-weighted on `mw_1`;
reproducible script to be added with the implementation.

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

### 2. Source split by year (proposed, not yet implemented)

EIA and ERCOT list many of the same projects under different names: matching by name and
county links only about 10% of them, so the lists cannot simply be merged. Proposal:

| Part | Source |
| --- | --- |
| Today's fleet and announced retirements | EIA-860M |
| New projects with a planned online year up to 2027 | EIA-860M planned (table 1) |
| New projects with a projected online date from 2028 | ERCOT GIS report (table 3), replacing EIA's 2028+ entries |

Risk: a project in EIA for 2027 that ERCOT lists for 2028 is counted twice. Likely small;
to be measured when implemented and recorded in the register.

### 3. ERCOT GIS projects from 2028 (proposed, not yet implemented)

Stage from the report's milestone dates. For projects with a signed agreement, odds come
straight from ERCOT's history with one rule: **low = share already operating, mid = operating
+ half of still-in-progress, high = operating + all still-in-progress.**

| Stage | Wind | Gas | Solar | Batteries | Delay (low / mid / high) |
| --- | --- | --- | --- | --- | --- |
| Construction started | 80 / 90 / 95% | same | same | same | 1 / 0 / 0 |
| Agreement signed | 69 / 74 / 80% | 54 / 56 / 57% | 50 / 67 / 83% | 42 / 66 / 90% | 1 / 0 / 0 |
| Study only | 10 / 20 / 30% | same | same | same | 2 / 1 / 0 |

Study only sits below ERCOT's 24% eventual completion because a project still in study must
also sign an agreement and build (1.8 to 3.3 years) to make 2030.

Capacity conversion: ERCOT reports nameplate MW; convert to summer MW with today's fleet ratios
from EIA-860M (gas 0.89, solar 1.00, wind 1.00, batteries 0.99).

### 4. Other

- Planned batteries: 1.7 hours of storage (today's ERCOT fleet average, 33 GWh / 19.4 GW).
- Retirements: only announced dates (about 1.4 GW by 2030).
- Fermi America's 4.5 GW of planned nuclear (Carson County) is for 2031-2032, after the horizon.

## What this does not cover

- Behind-the-meter generation at data centers (decided in v3).
- Accredited capacity: how much each fuel delivers in the tightest hours. That is what the
  hourly model in v3 tests; installed GW overstates solar and wind at evening peaks.
- Gas turbine supply limits and wind permitting headwinds beyond what ERCOT's history shows.

## Decisions for review

- [ ] EIA status odds (table 1), including the ERCOT-based changes to T, L and P?
- [ ] Delays as proposed?
- [ ] Source split by year: EIA to 2027, ERCOT GIS from 2028 (table 2)?
- [ ] ERCOT GIS stage odds and the low / mid / high rule (table 3)?
- [ ] 1.7-hour duration for planned batteries, and nameplate-to-summer conversion for ERCOT MW?
