# Supply assumptions (v2): proposal for review

Status: **proposed, pending review.** Values live in
[`config/assumptions.yaml`](../config/assumptions.yaml) under `supply`; every assumption is
also in the [register](assumptions.md) (section F). Run `uv run gridkeepup supply`.

## The question

How much generation and storage will ERCOT have each year to 2030, by fuel?

## First result (proposed values)

Total installed capacity, net summer GW (expected values):

| Year | Low | Mid | High |
| --- | --- | --- | --- |
| Today (Oct 2026) | 176.5 | 176.5 | 176.5 |
| 2026 (year end) | 185.0 | 188.9 | 189.2 |
| 2028 | 198.3 | 205.9 | 216.2 |
| 2030 | 208.9 | 216.8 | 224.4 |

Mid case 2030 by fuel: gas 66.0 GW (+3.8 on today), solar 56.9 (+23), wind 43.5 (+2.7),
storage 30.7 GW / 52 GWh (+11), coal 13.1 (-0.5), nuclear 5.0 (flat). The 2026 jump is the
9.4 GW of projects already built and waiting for commercial operation.

**Read the 2029-2030 flattening with care:** it reflects what developers have reported to
EIA so far, not a slowdown. Solar and batteries take one to two years to build, so most
2029-2030 projects are not in EIA-860M yet. ERCOT's interconnection queue fills that gap.

## Evidence

1. **Near-term plans mostly happen.** Of capacity developers planned for the next year,
   78% came online on schedule (EIA, 2017 cohort); in 2024 developers planned 36 GW of solar
   and 31 GW was installed. Cancellations are rare: under 1% of planned solar capacity a month.
   [EIA 2018](https://www.eia.gov/todayinenergy/detail.php?id=36513),
   [EIA 2025](https://www.eia.gov/todayinenergy/detail.php?id=66604)
2. **Delays are common but short.** About 20% of planned solar capacity reported a delay in
   Q3 2025, mostly one to two months before start-up.
   [EIA 2025](https://www.eia.gov/todayinenergy/detail.php?id=66604)
3. **Early-stage projects mostly fail.** Only 13% of capacity that requested interconnection
   from 2000 to 2020 reached commercial operation by end-2025; ERCOT has the best rate, 22%.
   [LBNL Queued Up 2026](https://emp.lbl.gov/publications/queued-2026-edition-characteristics),
   [Texas Tribune](https://www.texastribune.org/text/229163/)
4. **ERCOT's planned pipeline (EIA-860M, Oct 2026):** 9.4 GW built and awaiting commercial
   operation (TS), 18.3 GW under construction (U, V), 5.9 GW approved (T), 14.9 GW in
   approvals (L), 37.2 GW not yet in approvals (P).

## Proposed values

Chance a planned unit reaches operation, by EIA-860M status:

| Status | Meaning | Low | Mid | High | Delay added (low / mid / high) |
| --- | --- | --- | --- | --- | --- |
| TS | Built, awaiting commercial operation | 98% | 99% | 100% | 0 / 0 / 0 |
| V | Under construction, more than 50% | 90% | 95% | 100% | 1 / 0 / 0 |
| U | Under construction, 50% or less | 80% | 90% | 95% | 1 / 0 / 0 |
| T | Approvals received, not under construction | 50% | 65% | 80% | 1 / 1 / 0 |
| L | Approvals pending | 30% | 45% | 60% | 2 / 1 / 0 |
| P | Planned, no approvals yet | 15% | 25% | 40% | 2 / 1 / 1 |

Reasoning: construction-stage odds sit near EIA's 78-86% on-schedule history (and most of
the rest arrives within a year); P-stage odds sit just above ERCOT's 22% queue completion,
since a project reported to EIA is usually further along than a bare queue request.

Planned batteries: 1.7 hours of storage, the current ERCOT fleet average.

## What this does not cover yet

- Projects in ERCOT's interconnection queue but not yet in EIA-860M (the main gap for
  2029-2030). Needs ERCOT's monthly Generator Interconnection Status report.
- Fuel-specific odds (wind permitting headwinds, gas turbine supply limits).
- Behind-the-meter generation at data centers (decided in v3).
- Accredited capacity: how much each fuel can be counted on in the tightest hours. That is
  exactly what the hourly model in v3 tests.

## Decisions for review

- [ ] Status-based completion probabilities as above?
- [ ] Delays as above?
- [ ] 1.7-hour duration for planned batteries?
- [ ] Add ERCOT's interconnection queue for 2029-2030 (recommended), or keep EIA-860M only
  and state the gap?
- [ ] Fuel-specific adjustments now, or leave for later?
