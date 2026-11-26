# Demand assumptions (v1)

Status: **decided 2026-11-26.** The values below are in
[`config/assumptions.yaml`](../config/assumptions.yaml); change them there and rerun
`uv run gridkeepup demand`. Figures from secondary sources stay flagged in `data/manual/`
until checked against ERCOT's slides.

Every assumption, including the ones in code, is in the full
[assumptions register](assumptions.md).

## Result (mid case, 2030)

About 19.2 GW of new data center capacity connects or finishes ramping by 2030, but with
ramp-up only 13.0 GW is drawing power that year: **+11.7 GW at system peak and +80 TWh a
year** (ERCOT used 464 TWh in 2024). Low and high: +6.5 and +21.8 GW at peak. This is on
top of the ~3.9 GW large loads already drew in March 2026.

## Changes after the cross-check (2026-11-26)

Epoch AI's frontier campuses in Texas alone added more power in 2027 than the first version
of the model. Two causes: (1) load already energized but still ramping inside its existing
connection was missed, because all 5.9 GW of energized load was treated as baseline although
only ~3.9 GW was drawing; (2) hybrid campuses with on-site gas make Epoch's facility power
overstate grid demand. Fix: split the energized load into *drawing* (baseline, 3.9 GW) and
*still ramping* (2.0 GW, 2026 to 2027, not affected by the pause). Behind-the-meter
generation is a stated caveat until v2/v3. With the fix, the high scenario covers Epoch's
likely-ERCOT sites from 2027 (`uv run gridkeepup crosscheck`).

## The question

How many GW of new data center load connect to ERCOT each year from 2026 to 2030,
in a low, mid and high scenario?

## What the evidence says

1. **The queue is mostly not real yet.** In April 2026, of 445.8 GW of large-load
   applications through 2033, 321 GW had no studies submitted, 93.7 GW was under review and
   22 GW had met the Section 9.5 requirements. Only 5.9 GW of large loads was observed
   energized, with 3.2 GW more approved to energize but not yet operational. [1]
2. **Even approved load ramps slowly.** Of the ~9 GW of large loads approved to
   energize, ERCOT observed a non-simultaneous peak of ~3.9 GW: well under half is
   actually drawing power. [2]
3. **ERCOT's own history discounts promises.** Officer-letter loads with 2024 in-service
   dates delivered 55.4% of the project's load [3], and ERCOT's adjusted forecast applies a
   180-day delay to promised ramp schedules [4].
4. **ERCOT has already sorted the queue.** Its Batch Zero review (Sep 2026) conditionally
   classified 66.4 GW as *base load* (204 projects), ~127.9 GW as *studied load* (158
   projects) and excluded 302.2 GW (373 projects). Final decisions are due December 2026. [5]
5. **New data centers are on hold.** Since 3 August 2026 ERCOT has paused energizing new
   large data centers and crypto sites (75 MW or more) until a verification audit and a
   community-impact review finish; both reports are due by 10 December 2026. [5]
6. **Data centers don't run at nameplate.** Average GPU utilization is "probably closer to
   70%" even for training [6], while many planning studies assume a 90% load factor [7].

## Proposed model structure

Use ERCOT's Batch Zero categories as the stages, since they are the most recent and most
rigorous filter available:

```
new DC GW in year Y = sum over stages ( stage GW x P(connect by 2030 | stage) x ramp(Y) )
```

## Proposed values

**Probability that a stage's MW is connected and running by 2030** 

| Stage | GW | Low | Mid | High | Reasoning |
| --- | --- | --- | --- | --- | --- |
| Energized, drawing (in baseline) | 3.9 | 100% | 100% | 100% | Already drawing power, so already in historical demand |
| Energized, still ramping | 2.0 | 80% | 90% | 100% | Connected but not yet at full draw; ramps over 2 years from 2026 |
| Approved, not yet operational | 3.2 | 50% | 75% | 100% | Approved; ERCOT's 55% officer-letter history sets the low end |
| Batch Zero base load | 66.4 | 10% | 20% | 40% | Studied and prioritised, but 2030 is close and the pause delays everything |
| Batch Zero studied load | ~127.9 | 1% | 3% | 8% | Earlier stage; most will slip past 2030 or cancel |
| Excluded | 302.2 | 0% | 0% | 0% | Not in ERCOT's planning cases |

**Connected by 2030** (stage GW x probability; the first row is already connected)

| Scenario | New data center capacity (x 90% share), incl. still-ramping load |
| --- | --- |
| Low | 10.0 GW |
| Mid | 19.2 GW |
| High | 37.8 GW |

**Timing**: nothing new energizes before 2027 because of the pause; each connected project
ramps linearly to full load over 3 years (consistent with only ~43% of approved load drawing
power today). Within that, implementation choices: approved-but-not-operational load
connects in 2027 (first in line), base load spreads evenly over 2027 to 2030, and studied
load over 2028 to 2030 (it needs more study first).

**Load factor** : 0.70 average (energy), 0.90 of nameplate during system
peak hours (data centers don't back off at peak unless they are flexible; v4 tests that).

## Cross-checks to run in v1

- ERCOT's adjusted long-term load forecast and its Batch Zero load forecast for 2030
- The share of national data center growth Texas would capture under each scenario
  (analysts expect roughly 65 GW of US data center growth through 2030)
- Epoch AI's Texas sites: the bottom-up total should sit inside the mid scenario near term

## Decisions (2026-11-26)

- [x] Batch Zero categories as stages
- [x] Probabilities as proposed
- [x] 3-year ramp, no new energizations before 2027
- [x] Load factor 0.70 average, 0.90 at peak
- [x] Crypto mining excluded from new demand. Miners curtail in tight hours, so they add
  little at peak; queue stages are scaled by the ~90% data center share, and existing
  crypto is already in the historical baseline. One switch (`include_crypto`) flips it.
- [x] Load already drawing power (3.9 GW) is baseline; energized load still ramping (2.0 GW)
  is new demand (revised after the Epoch cross-check).
- [x] Behind-the-meter generation stated as a caveat in v1; modelled in v2/v3.

## Sources

1. Data Center Frontier, "ERCOT puts Texas AI megawatts to the test", citing ERCOT's April 2026 monthly report. https://www.datacenterfrontier.com/energy/article/55401760/ercot-puts-texas-ai-megawatts-to-the-test
2. ERCOT, March 2026 TAC report, Large Load Interconnection Status Update. https://www.ercot.com/files/docs/2026/03/12/March-TAC-Report.pdf
3. ERCOT, 2025 RTP Load Update (June 2025). https://www.ercot.com/files/docs/2025/06/17/2025_RTP_Load_Update_June_2025_RPG.pdf
4. ERCOT, 2025 Long-Term Load Forecast report. https://www.ercot.com/files/docs/2025/04/08/2025_LTLF_Report.docx
5. ERCOT Board, Item 14: Batch Zero Update (September 2026). https://www.ercot.com/files/docs/2026/09/11/14-Batch-Zero-Update.pdf
6. Uptime Institute Intelligence. https://intelligence.uptimeinstitute.com/pdf-download/node/101800
7. Examples collected at https://themariojude.com/Puzzle+of+low+data+center+utilisation
