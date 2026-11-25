# Manual inputs

Numbers that only exist in PDFs or press coverage, typed in by hand. Every row
carries its source and a `verified` flag.

`verified = false` means the number came from a secondary source or a search
excerpt and has **not yet been checked against the original ERCOT slide**.
Checking them (open the URL, find the figure, flip the flag to `true`, fix the
number if needed) is part of v0.

| File | What |
| --- | --- |
| `ercot_large_load_queue.csv` | Total large-load interconnection requests tracked by ERCOT over time, and the data center share |
| `ercot_large_load_stages.csv` | The same queue split by study stage (feeds the v1 connection probabilities) |
| `ercot_reference.csv` | Reference points such as ERCOT's all-time peak demand |
