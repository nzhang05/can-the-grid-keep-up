# Demand assumptions (v1): proposal for review

Status: **proposed, not yet decided.** Every number below marked *proposed* is a starting
point to be accepted, changed or replaced. Sources are listed at the end; figures taken
from secondary sources are flagged in `data/manual/` until checked against ERCOT's slides.

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

**Probability that a stage's MW is connected and running by 2030** (*proposed*)

| Stage | GW | Low | Mid | High | Reasoning |
| --- | --- | --- | --- | --- | --- |
| Observed energized | 5.9 | 100% | 100% | 100% | Already on the system |
| Approved, not yet operational | 3.2 | 50% | 75% | 100% | Approved; ERCOT's 55% officer-letter history sets the low end |
| Batch Zero base load | 66.4 | 10% | 20% | 40% | Studied and prioritised, but 2030 is close and the pause delays everything |
| Batch Zero studied load | ~127.9 | 1% | 3% | 8% | Earlier stage; most will slip past 2030 or cancel |
| Excluded | 302.2 | 0% | 0% | 0% | Not in ERCOT's planning cases |

**Resulting nameplate data center load by 2030** (arithmetic on the table)

| Scenario | GW |
| --- | --- |
| Low | ~15 |
| Mid | ~25 |
| High | ~46 |

**Timing** (*proposed*): nothing new energizes before 2027 because of the pause; each
connected project ramps linearly to full load over 3 years (consistent with only ~43% of
approved load drawing power today).

**Load factor** (*proposed*): 0.70 average (energy), 0.90 of nameplate during system
peak hours (data centers don't back off at peak unless they are flexible; v4 tests that).

## Cross-checks to run in v1

- ERCOT's adjusted long-term load forecast and its Batch Zero load forecast for 2030
- The share of national data center growth Texas would capture under each scenario
  (analysts expect roughly 65 GW of US data center growth through 2030)
- Epoch AI's Texas sites: the bottom-up total should sit inside the mid scenario near term

## Decisions for review

- [ ] Use Batch Zero categories as stages (instead of the April 2026 study stages)?
- [ ] Accept, change or replace the probabilities above
- [ ] 3-year ramp and no new energizations before 2027?
- [ ] Load factor 0.70 average and 0.90 at peak?
- [ ] Count crypto mining? (ERCOT's energized large loads include it; it is highly flexible)

## Sources

1. Data Center Frontier, "ERCOT puts Texas AI megawatts to the test", citing ERCOT's April 2026 monthly report. https://www.datacenterfrontier.com/energy/article/55401760/ercot-puts-texas-ai-megawatts-to-the-test
2. ERCOT, March 2026 TAC report, Large Load Interconnection Status Update. https://www.ercot.com/files/docs/2026/03/12/March-TAC-Report.pdf
3. ERCOT, 2025 RTP Load Update (June 2025). https://www.ercot.com/files/docs/2025/06/17/2025_RTP_Load_Update_June_2025_RPG.pdf
4. ERCOT, 2025 Long-Term Load Forecast report. https://www.ercot.com/files/docs/2025/04/08/2025_LTLF_Report.docx
5. ERCOT Board, Item 14: Batch Zero Update (September 2026). https://www.ercot.com/files/docs/2026/09/11/14-Batch-Zero-Update.pdf
6. Uptime Institute Intelligence. https://intelligence.uptimeinstitute.com/pdf-download/node/101800
7. Examples collected at https://themariojude.com/Puzzle+of+low+data+center+utilisation
