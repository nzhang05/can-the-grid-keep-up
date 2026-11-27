# Assumptions register

Every assumption in the project, in one place: what it is, the value, why, where it lives,
and who decided it. If it shapes a number in a chart or a post, it is listed here.

**Status key**
- **Decided**: chosen by the project owner after review
- **Proposed**: drafted for review, used in results until decided
- **Implementation**: a modelling choice made while building, open to challenge
- **Convention**: a data-handling rule with little effect on results
- **Open**: to be set in a later version
- **Derived**: computed from data with a stated method (see derived-values.md)

Values for anything in `config/assumptions.yaml` live there; change them in the config and
rerun. Values computed from data (marked **Derived**) are recomputed from the raw files by
`uv run gridkeepup derive`, which writes the inputs and arithmetic to
[derived-values.md](derived-values.md); a test fails if the config and the data disagree. A test (`tests/test_assumptions_documented.py`) fails if a config assumption is not
listed in this file.

Last reviewed: 2026-11-27 (v1 and v2 decided).

## A. Scope

| ID | Assumption | Value | Rationale | Where | Status |
| --- | --- | --- | --- | --- | --- |
| A1 | Region | ERCOT only (`name: ERCOT`) | One grid operator, best public data, largest queue | config `region` | Decided |
| A2 | Horizon | `start_year` 2026 to `end_year` 2030 | Start short; extend to 2033 (ERCOT's reporting horizon) later | config `horizon` | Decided |
| A3 | Crypto mining | Out of scope for new demand (`include_crypto: false`) | Miners curtail in tight hours, adding little at peak; existing crypto is in the historical baseline | config `demand` | Decided |
| A4 | System-level adequacy only | No transmission, local constraints, prices or water | Network models are not public | README | Decided |
| A5 | Behind-the-meter generation | Not yet modelled; stated as a caveat | Hybrid campuses (e.g. Stargate Abilene, ~1 GW on-site gas) draw less from the grid than their facility power, especially at peak. Modelled in v2/v3 as both a demand reducer and a supply source | this file, README | Decided (caveat for v1) |

## B. Data sources and conventions

| ID | Assumption | Value | Rationale | Where | Status |
| --- | --- | --- | --- | --- | --- |
| B1 | Hourly demand and generation source | EIA-930 via EIA API v2, respondent `eia_respondent: ERCO` | Reachable from outside the US (ERCOT's own API reportedly is not); covers ERCOT | config `region`, `fetch/eia930.py` | Decided |
| B2 | History used as weather years | `first_year` 2019 to `last_year` 2025 | Includes Winter Storm Uri (2021) and the 2023 heat | config `history` | Decided |
| B3 | Timestamps | UTC, hour-beginning; MWh per hour = average MW | EIA's `hourly` frequency | `fetch/eia930.py` | Convention |
| B4 | Calendar years | Texas local time (US/Central) for annual peaks, energy and quality | Matches how ERCOT reports peaks | `clean.py`, `charts.py` | Convention |
| B5 | Generator inventory | EIA-860M, filtered to `eia860m_balancing_authority: ERCO` (`state: TX` kept for reference) | The BA filter excludes Texas plants in SPP/MISO/WECC | config `region`, `fetch/eia860m.py` | Decided |
| B6 | EIA-860M header row | Found by the `Entity ID` column header | EIA puts notes above the table and changes layout over time | `fetch/eia860m.py` | Convention |
| B7 | Hand-entered figures | Typed from ERCOT slides and press coverage, each with a source URL and `verified` flag | Only exist in PDFs; flags show what is not yet checked against the original slide | `data/manual/` | Convention |
| B9 | ERCOT interconnection queue | ERCOT GIS report, October 2026 (`Project Details - Large Gen`), downloaded by hand to `data/raw/ercot_gis/` | Project-level stages and projected online dates for 446 GW | data | Convention |
| B10 | Completion history | LBNL Queued Up data file through 2025 (`03. Complete Queue Data`, ERCOT rows, capacity-weighted), downloaded by hand to `data/raw/lbnl/` (CC BY 4.0) | Only public project-level record of which requests reached operation | data | Convention |
| B8 | All-time peak | 91,134 MW, 22 Jul 2026 (unofficial) | ERCOT Monthly Operational Overview, Jul 2026 | `data/manual/ercot_reference.csv` | Convention (unverified) |

## C. Cleaning

| ID | Assumption | Value | Rationale | Where | Status |
| --- | --- | --- | --- | --- | --- |
| C1 | Short gaps | Interpolate gaps of up to `MAX_FILL_HOURS` = 6 h; longer gaps stay missing | A few missing hours are safely interpolated; whole missing days (e.g. 5 Dec 2025) need a better method in v3 | `clean.py` | Implementation |
| C2 | Bad values | Zero or negative demand, and one-hour spikes beyond `SPIKE_RATIO` = 1.5x both neighbours, are set aside and filled | Typical EIA-930 reporting glitches; none found in 2019 to 2024 ERCOT data | `clean.py` | Implementation |
| C3 | Winter Storm Uri | Hours from 15 Feb 2021 06:00 to 19 Feb 2021 06:00 UTC flagged in `KNOWN_EVENTS` | Reported load reflects forced outages, not demand; v3 must adjust it | `clean.py` | Implementation |
| C4 | Storage categories | `STORAGE_FUELS` (BAT, UES) keep negative values (charging); other fuels clipped at 0 | Storage is net output | `clean.py` | Convention |
| C5 | Late-starting fuel categories | 0 before EIA's first report (battery storage from 2024), not a gap | EIA added the category; earlier batteries sat in other categories | `clean.py` | Convention |
| C6 | Annual peaks on charts | Only years with at least `MIN_HOURS_FOR_PEAK` = 8,700 hours | Skips stub years at the UTC/Texas year boundary | `charts.py` | Convention |

## D. Demand (v1)

Formula: new data center GW = stage GW x P(connect by horizon end) x data center share,
spread over connection years, then ramped linearly to full load.

| ID | Assumption | Value | Rationale | Where | Status |
| --- | --- | --- | --- | --- | --- |
| D1 | Queue stages | ERCOT Batch Zero categories (Sep 2026) plus already-connected load, in `stages` | Most recent and most rigorous filter of the queue | config `demand.stages` | Decided |
| D2 | Energized, drawing (in baseline) | 3.9 GW, `in_baseline: true` | ERCOT observed ~3.9 GW peak draw from energized large loads (Mar 2026); it is in the historical demand, so not counted again | config | Decided |
| D3 | Energized, still ramping | 2.0 GW (5.9 energized - 3.9 drawing); `p_connect` 80% / 90% / 100%; `connect_years` 2026; `ramp_years` 2 | Already connected sites keep ramping inside existing connections; the pause does not stop this | config | Decided |
| D4 | Approved, not yet operational | 3.2 GW; 50% / 75% / 100%; connects 2027 | Approved; ERCOT's 55% officer-letter history sets the low end; first in line after the pause | config | Decided (timing: Implementation) |
| D5 | Batch Zero base load | 66.4 GW; 10% / 20% / 40%; spread 2027 to 2030 | Studied and prioritised, but 2030 is close and the pause delays everything | config | Decided (timing: Implementation) |
| D6 | Batch Zero studied load | ~127.9 GW (chart shows 125.4); 1% / 3% / 8%; spread 2028 to 2030 | Earlier stage; most will slip past 2030 or cancel | config | Decided (timing: Implementation) |
| D7 | Excluded | 302.2 GW; 0% in all scenarios | Not in ERCOT's planning cases | config | Decided |
| D8 | Data center share | `datacenter_share` 0.90, applied to every non-baseline stage | ERCOT: ~90% of large-load requests are data centers (Jun 2026). Likely overstates data centers in the energized stage, where crypto is a larger share | config | Decided |
| D9 | First new connection year | `first_new_connection_year` 2027 | Energization pause since 3 Aug 2026; reports due 10 Dec 2026 | config | Decided |
| D10 | Ramp | `ramp_years` 3, linear, mid-year convention: year k after connection draws (k + 0.5) / 3 of nameplate | Only ~43% of approved large-load capacity drew power in Mar 2026 | config, `demand.py` | Decided (convention: Implementation) |
| D11 | Even spreading | A stage's connected MW is split evenly over its `connect_years` | No project-level dates for most of the queue | `demand.py` | Implementation |
| D12 | Load factor | `load_factor` 0.70 (average draw / nameplate) | GPU utilisation averages ~70% even for training (Uptime Institute) | config | Decided |
| D13 | Peak factor | `peak_factor` 0.90 (draw at system peak / nameplate) | Non-flexible data centers do not back off at peak; v4 tests flexibility | config | Decided |
| D14 | Facility vs IT power | `facility_to_it_power` 1.3 | Epoch AI's typical ratio; matches the median in Epoch's timelines | config | Convention |
| D15 | Queue MW are grid-facing nameplate | Queue figures are treated as facility (grid) MW, not IT MW | ERCOT large-load requests are for grid service | `demand.py` | Implementation |
| D16 | Baseline vintage | Historical data ends in 2025, but D2's 3.9 GW is a Mar 2026 observation | Some of the 3.9 GW is not yet in the 2025 data; v3 must grow the baseline to 2026 so it is neither missed nor double counted | this file | Open (v3) |

## E. Cross-check against Epoch AI (v1)

| ID | Assumption | Value | Rationale | Where | Status |
| --- | --- | --- | --- | --- | --- |
| E1 | Epoch is a subset | Model should be at or above Epoch's Texas buildout | Epoch tracks only frontier AI campuses (12 Texas sites) | `epoch.py` | Convention |
| E2 | Start date | Growth counted from `epoch_since` 2026-08-01 | Start of the energization pause | config `crosscheck` | Implementation |
| E3 | Texas filter | Address contains "TX" or "Texas" | Epoch has no grid field | `epoch.py` | Convention |
| E4 | Possibly not in ERCOT | `epoch_possibly_not_ercot`: Goodnight (Claude, TX), Coreweave Helios (Afton, TX) | Panhandle / South Plains utilities can be in SPP; excluded until checked | config `crosscheck` | Open (verify utility) |
| E5 | Planned dates count | Epoch's future timeline entries are taken at face value | They are announced schedules; they may not reflect the pause, and facility power overstates grid draw for hybrid sites (A5) | `epoch.py` | Implementation |
| E6 | Known gap | Late 2026: Epoch shows +0.7 GW, model high +0.45 GW | Explained by E5 (announced schedules, on-site gas), not adjusted for | this file | Accepted |

## F. Supply (v2)

Formula: capacity(fuel, year) = today's operating fleet - planned retirements + planned
units x P(built | stage) once their planned year + delay has passed; ERCOT queue projects
with a signed agreement or in study are timed by completion curves (F19-F23). Expected values.
Rationale and evidence: [supply-assumptions.md](supply-assumptions.md). Decided 2026-11-27.

| ID | Assumption | Value | Rationale | Where | Status |
| --- | --- | --- | --- | --- | --- |
| F1 | Snapshot | `snapshot_year` 2026: EIA-860M October 2026 operating fleet is "today" (176.5 GW) | Latest inventory available | config `supply` | Convention |
| F2 | Capacity measure | Net summer MW | ERCOT peaks in summer; summer capacity is what plants can deliver in heat | `supply.py` | Implementation |
| F3 | Completion probability by EIA status | `status_probability`: TS 98/99/100%, V 90/95/100%, U 80/90/95%, T 45/56/70%, L 30/40/55%, P 15/24/35%, OT 25/40/60% (low/mid/high) | T mid = share of ERCOT capacity operating after signing an agreement (2000-2022 agreements: 56.1%); P mid = share of all ERCOT requests 2000-2020 operating (24.3%); construction stages from EIA's 78-86% on-schedule history; other values set around these anchors, monotonic by stage | config `supply` | Decided (T and P mid: Derived) |
| F4 | Delays | `status_delay_years` added to the planned year: 0 for TS; low case +1 year for V/U/T and +2 for L/P; mid +1 for T/L/P | ~20% of planned solar reports a delay, mostly short; completed ERCOT projects came online close to their last reported date; early-stage projects slip more | config `supply` | Decided |
| F5 | Planned battery duration | `planned_storage_hours` 1.7 h | Derived: EIA-860M has no MWh for planned batteries, so they get today's ERCOT fleet average: 33,021 MWh / 19,605 MW nameplate across 270 operating batteries = 1.68, rounded to 1.7 h | config `supply` | Derived |
| F6 | Planned retirements | Units retire in their reported `planned_retirement_year` (~1.4 GW by 2030); no unannounced retirements | Only announced dates are public | `supply.py` | Implementation |
| F7 | Expected values | A 500 MW unit at 25% adds 125 MW; no project-by-project draws | Simple and transparent; v3 can add uncertainty if needed | `supply.py` | Implementation |
| F8 | Fuel groups | EIA technologies mapped to Nuclear, Coal (incl. petroleum coke), Gas, Wind, Solar, Storage, Hydro, Other | For charts and the adequacy model | `supply.py` (`FUEL_GROUPS`) | Convention |
| F9 | Reporting horizon | Only projects already in EIA-860M count. Fast-to-build solar and storage for 2029-2030 are mostly not reported yet, so later years are understated | Fixed: ERCOT queue from 2028 (F13), timed by F19 | this file | Resolved |
| F10 | No fuel-specific odds | Same status odds for every fuel | Wind faces federal permitting headwinds and gas faces turbine supply limits, but no clean source yet for fuel-specific rates | this file | Open |
| F11 | Behind-the-meter generation | Not in supply (on-site gas at data centers, e.g. Fermi America's planned 780 MW) | Decided in v3 as a peak-demand reducer (A5) | this file | Open (v3) |
| F12 | Fermi America nuclear | 4.5 GW planned for 2031-2032 (status P) | After the 2030 horizon; no effect on v2 | data | Convention |
| F13 | Source split by year | `ercot_gis` `first_year` 2028: EIA-860M for the fleet, retirements and projects planned up to 2027; ERCOT GIS report for projects with projected online dates from 2028, replacing EIA's 2028+ entries. `enabled` (true) switches the queue on or off | The two lists name projects differently (name + county matching links ~10%), so they cannot be merged; a year split avoids double counting | config `supply.ercot_gis` | Decided |
| F14 | ERCOT GIS stage odds | `stage_probability`: synchronized and energized 98/99/100% (as EIA TS); construction 80/90/95% (as EIA U); signed by fuel: wind 69/74/80%, gas 54/56/57%, solar 50/67/83%, storage 42/66/90%, other (nuclear, hydro, other) 56/64/73%; study by fuel: wind 28/31/34%, gas 27/29/32%, solar 23/34/46%, storage 13/39/66%, other 24/32/39%. Signed and study are eventual odds (the level of F19's curves) | Derived from ERCOT history (LBNL), low = share operating, mid = + half still in progress, high = + all still in progress; other = all-fuel rate. Signed: agreements signed 2000-2022. Study: all requests submitted 2000-2020 (replaced a 10/20/30% placeholder that tried to fold timing into the odds) | config `supply.ercot_gis` | Derived |
| F15 | ERCOT GIS delays | `stage_delay_years`: synchronized and energized 0; construction +1 / 0 / 0 (low / mid / high). Signed and study have no fixed delay: timed by F19 | As F4 | config `supply.ercot_gis` | Decided |
| F16 | Nameplate to summer MW | `summer_ratio`: gas 0.89, solar 1.0, wind 1.0, storage 0.99, other 1.0 | Derived: ERCOT reports nameplate MW; ratio = net summer MW / nameplate MW of today's operating fleet (e.g. gas 62,175 / 69,930 = 0.89). Other set to 1.0 (too few queued projects to matter) | config `supply.ercot_gis` | Derived |
| F17 | Double counting at the 2027/2028 boundary | Name + county matching finds 18 projects (3.5 GW nameplate) listed by EIA for 2026-2027 and by ERCOT for 2028 | Loose matching, so an indication; `supply.boundary_overlap()` lists them | this file | Accepted (measured) |
| F18 | ERCOT fuel codes | GIS "OTH" with technology "BA" = batteries | 828 of 832 OTH projects are BA | data | Convention |
| F19 | Queue timing | `timing: curves`. For signed and study-only queue projects: P(online by year Y) = (G(a + Y - 2026) - G(a)) / (1 - G(a)), where a = years since signing (signed) or queue entry (study) and G = ERCOT's completion curve for that fuel rescaled to the F14 eventual odds; 0 before the projected online year. Replaces applying eventual odds at the projected date, which put 44 GW in 2028 (3x ERCOT's record 15.3 GW) | ERCOT history: completion spreads over years (3-24% online within 2 years of signing, 39-75% within 4). Conditioning on age means a project that signed long ago and is still not built gets lower near-term odds | config `supply.ercot_gis.timing`; `supply.online_by` | Decided |
| F20 | Completion curves | Share of capacity online within k years (k = 0-12) of signing (basis `signed`, from `ia_date`) or queue entry (basis `queue`, from `q_date`), by fuel plus all-fuel. Cohorts with k full years of follow-up only (start year <= 2025 - k); capacity-weighted; non-decreasing; under 0.5 GW of sample repeats the previous value; fuels without a curve use all-fuel | Derived from LBNL ERCOT rows by `gridkeepup derive`; committed as `data/derived/completion_curves.csv` so the model runs without the LBNL file; a test checks the CSV against the data | `data/derived/completion_curves.csv` | Derived |
| F21 | Thin curve samples | Battery `signed` curve rests on 0.7 GW or less from year 4 (0.08 GW by year 12); battery `queue` curve on under 2 GW from year 6; solar `signed` on under 2 GW from year 10 | The ERCOT battery boom is recent; values are carried forward rather than dropped. Most battery capacity in the queue signed in 2024-2026, so years 0-5 of the curve matter most | derived-values.md | Accepted (measured) |
| F22 | Timing backtest | Replaying F19-F20 on ERCOT's queue at end-2019, 2020 and 2021 (curves rebuilt from data to that year, mid odds, no tax factor) predicted 17.2 / 18.7 / 21.8 GW over the next 4 years; actual 23.2 / 33.1 / 35.2 GW (actual / model 1.35-1.77) | The method runs low on history (partly because projects already under construction are counted as signed in the replay). The high 2028-2030 additions come from the queue's size, not the method | `derive.backtest`; derived-values.md | Measured |
| F23 | Tax-credit cliff | `tax_credit_factor`: queue Solar and Wind at stages signed and study get odds x 0 / 0.5 / 1 (low / mid / high). Storage, gas and projects under construction unaffected | Federal wind and solar credits end for projects starting construction after 4 Jul 2026 and in service after 2027 (OBBBA, 2025). History has no such break, and ERCOT's report does not show tax-purpose construction starts. Judgment bracket (none / half / all proceed), not derived. Mid 2030 effect: -21.5 GW | config `supply.ercot_gis.tax_credit_factor` | Decided (judgment) |
| F24 | No build-rate limit | The model does not cap how much ERCOT can connect or developers can build in a year. Mid additions are 27-29 GW/yr in 2028-2030 vs a record 15.3 GW (2025); low is 13-17 GW/yr | No clean source for such a limit. Mid batteries (55 GW by 2029) sit at the top of Modo Energy's 40-55 GW outlook. Largest open uncertainty in supply | supply-assumptions.md | Accepted (stated) |

## G. Not yet decided

| ID | Assumption | Version |
| --- | --- | --- |
| G1 | Source behind completion rates (`completion_rate_source`): LBNL project data, computed (B10) | Done (v2) |
| G2 | Thermal outage rate (`thermal_forced_outage_rate`) | v3 |
| G3 | Growth of non-data-center demand (`non_datacenter_load_growth`) | v3 |
| G4 | Reliability standard used to judge shortfalls (`reliability_standard`: 1 day in 10 years) | v3 |
| G5 | How behind-the-meter generation enters demand and supply (A5, F11) | v3 |
| G6 | Filling whole missing days (C1) and adjusting Uri load (C3) | v3 |
