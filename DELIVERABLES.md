# DELIVERABLES.md — Base Submission Package

**Status:** FINAL — Defines the minimum deliverables for the base assignment.
**Governing documents:** SPEC.md (strategy rules), ASSUMPTIONS.md (resolved edge-case decisions).

This document defines the exact finish line for the base backtesting assignment. Every item listed below is mandatory. Anything not listed here is optional and belongs to the creative-extensions layer.

---

## §1 — Deliverable Inventory

| # | Deliverable | Type | Description |
|---|---|---|---|
| D1 | Source code | Code | Complete, runnable codebase that produces D3–D8 from raw data. |
| D2 | README.md | Document | Workflow/report document covering objectives, assumptions, run instructions, and findings. |
| D3 | `trades.csv` | Data | Every executed fill across the full backtest. |
| D4 | `positions_timeline.csv` | Data | Position state at every state change across the full backtest. |
| D5 | `mtm_timeline.csv` | Data | Per-second mark-to-market PnL across the full backtest. |
| D6 | `daily_summary.csv` | Data | One-row-per-day-per-underlier rollup of trades, rolls, and PnL. |
| D7 | Cumulative PnL plot | Chart | Time-series chart of running total PnL. |
| D8 | Daily PnL plot | Chart | Bar chart of per-day realized PnL. |
| D9 | Findings section | Text | Structured bullet-point observations inside D2. |

---

## §2 — CSV Schema Definitions

### D3 — `trades.csv`

**Governing rules:** SPEC.md Rule 11, ASSUMPTIONS.md A8, A13, A14, A17.

Each row represents one atomic fill. A roll produces 4 rows. An initial entry produces 2 rows. A forced square-off produces 2 rows.

| Column | Data type | Description |
|---|---|---|
| `trade_date` | `YYYY-MM-DD` | The trading day (derived from folder name, e.g. `NSE_20221101` → `2022-11-01`). |
| `timestamp` | `YYYY-MM-DD HH:MM:SS` | The exact second on the 1-second grid at which this fill occurs. |
| `underlier` | string | `NIFTY` or `BANKNIFTY`. |
| `expiry` | `YYYY-MM-DD` | Expiry date of the option contract (parsed from filename). |
| `strike` | integer | Strike price of the option contract (parsed from filename). |
| `option_type` | string | `CE` or `PE`. |
| `instrument_name` | string | Full instrument identifier as encoded in the filename, without `.csv` extension (e.g. `NIFTY22110317300CE`). |
| `direction` | string | `BUY` (entering a long position) or `SELL` (exiting a long position). |
| `price` | float | Fill price — the marked price on the 1-second grid at `timestamp` for this instrument (per A8). |
| `quantity` | integer | Always `1` (per SPEC.md Rule 6). |
| `reason` | string | One of: `ENTRY` (initial day entry per A13), `ROLL` (strike change per Rule 9), `SQUAREOFF` (end-of-day close per Rule 10). |

**Column name note:** the identifier column is emitted as `instrument_name` (not `instrument`). `expiry`, `strike`, and `option_type` are parsed from that name and included so the file is self-describing without re-parsing.

**Sort order:** `trade_date` ASC, `timestamp` ASC; within a single roll timestamp, SELL fills precede BUY fills so exits are booked before entries.

**Row count identity:** In the clean case, per underlier per day: `(2 × entries) + (4 × rolls) + (2 × squareoffs)` per A17. Under ASSUMPTIONS.md A5, a strike change whose new legs are momentarily unpriced is split into an exit now (2 SELL fills) and a re-entry later (2 BUY fills), so fills are not always an exact multiple of 4. The authoritative roll count is therefore `num_rolls` in D6 (counted from strike-change events in D4), not `ROLL fills ÷ 4`.

---

### D4 — `positions_timeline.csv`

**Governing rules:** SPEC.md Rule 11, ASSUMPTIONS.md A5, A13.

**Granularity choice: state-change rows, not per-second rows.**

Rationale: The position state changes only at entry, roll, flat transition, or square-off — typically a few to a few dozen times per day. A per-second dump would produce ~472,500 rows for 21 days (22,500 × 21) with >99% identical consecutive rows. State-change representation is compact, auditable, and satisfies Rule 11's requirement that "which instruments are held at any point in time" is recoverable: the position at any arbitrary second equals the most recent state-change row with `timestamp` ≤ that second for that underlier.

Each row represents a position state that **begins** at the given timestamp and **persists** until the next row for the same underlier on the same day (or until session end).

| Column | Data type | Description |
|---|---|---|
| `trade_date` | `YYYY-MM-DD` | The trading day. |
| `timestamp` | `YYYY-MM-DD HH:MM:SS` | The second at which this position state begins. |
| `underlier` | string | `NIFTY` or `BANKNIFTY`. |
| `state` | string | `FLAT` (no position held) or `HOLDING` (straddle active). |
| `strike` | integer or null | The held strike. Null when `state` = `FLAT`. |
| `ce_instrument` | string or null | Full CE instrument identifier (e.g. `NIFTY22110317300CE`). Null when `state` = `FLAT`. |
| `ce_entry_price` | float or null | Price at which the CE was entered. Null when `state` = `FLAT`. |
| `ce_entry_timestamp` | `YYYY-MM-DD HH:MM:SS` or null | Timestamp at which the CE was entered. Null when `state` = `FLAT`. |
| `pe_instrument` | string or null | Full PE instrument identifier (e.g. `NIFTY22110317300PE`). Null when `state` = `FLAT`. |
| `pe_entry_price` | float or null | Price at which the PE was entered. Null when `state` = `FLAT`. |
| `pe_entry_timestamp` | `YYYY-MM-DD HH:MM:SS` or null | Timestamp at which the PE was entered. Null when `state` = `FLAT`. |
| `ce_entry_timestamp` | `YYYY-MM-DD HH:MM:SS` or null | Second at which the CE leg was entered (equals `timestamp` of this HOLDING row). Null when `state` = `FLAT`. |
| `pe_entry_timestamp` | `YYYY-MM-DD HH:MM:SS` or null | Second at which the PE leg was entered (equals `timestamp` of this HOLDING row). Null when `state` = `FLAT`. |
| `trigger` | string | What caused this state: `ENTRY` (first entry of the day, or re-entry after a flat gap), `ROLL` (strike change per Rule 9), `FLAT_NO_PRICE` (position exited because the new closest strike lacks a valid price per A5, with no re-entry yet), `SQUAREOFF` (end-of-day close per Rule 10). |

**Granularity note:** only state *changes* are logged (not one row per second), so the timeline is compact. The position at any arbitrary second is the most recent row with `timestamp` ≤ that second for that underlier.

**Sort order:** `trade_date` ASC, `underlier` ASC, `timestamp` ASC.

**First row per day per underlier:** The first `ENTRY` row, at the first second both legs of the closest strike are priced (usually `09:15:00`, later if the ATM legs open late). The engine does not emit a separate `SESSION_START` placeholder row — the day simply begins with the first entry. If no strike is ever tradable that day the underlier stays flat and produces no HOLDING rows (per A20).

**Last row per day per underlier:** Always `trigger` = `SQUAREOFF`, `state` = `FLAT`, at `15:29:59` — unless the underlier was already flat into the close, in which case the last row is whatever preceded session end.

---

### D5 — `mtm_timeline.csv`

**Governing rules:** SPEC.md Rule 11, ASSUMPTIONS.md A9, A16.

**Granularity: one row per evaluated second.**

This is mandated by A16 ("at every evaluated second") and Rule 11 ("time-indexed series… at each evaluated second"). Expected row count: 22,500 seconds × 21 trading days = 472,500 rows.

| Column | Data type | Description |
|---|---|---|
| `trade_date` | `YYYY-MM-DD` | The trading day. |
| `timestamp` | `YYYY-MM-DD HH:MM:SS` | The evaluated second (from `09:15:00` to `15:29:59`). |
| `nifty_unrealized_pnl` | float | Unrealized PnL for NIFTY open positions at this second (per A9). `0.0` if flat. |
| `nifty_realized_pnl` | float | Cumulative realized PnL for NIFTY from all positions closed so far today. |
| `nifty_total_pnl` | float | `nifty_unrealized_pnl + nifty_realized_pnl`. |
| `banknifty_unrealized_pnl` | float | Unrealized PnL for BANKNIFTY open positions at this second (per A9). `0.0` if flat. |
| `banknifty_realized_pnl` | float | Cumulative realized PnL for BANKNIFTY from all positions closed so far today. |
| `banknifty_total_pnl` | float | `banknifty_unrealized_pnl + banknifty_realized_pnl`. |
| `combined_total_pnl` | float | `nifty_total_pnl + banknifty_total_pnl`. |

**Sort order:** `trade_date` ASC, `timestamp` ASC.

**End-of-day invariant:** At `15:29:59`, `nifty_unrealized_pnl` and `banknifty_unrealized_pnl` are both `0.0` (all positions squared off per Rule 10). Therefore `*_total_pnl` equals `*_realized_pnl` at session end.

---

### D6 — `daily_summary.csv`

**Governing rules:** Rollup of D3, D4, D5.

One row per trading day per underlier. For 21 days × 2 underliers = 42 rows.

| Column | Data type | Description |
|---|---|---|
| `trade_date` | `YYYY-MM-DD` | The trading day. |
| `underlier` | string | `NIFTY` or `BANKNIFTY`. |
| `num_trades` | integer | Total fill records in `trades.csv` for this day and underlier. |
| `num_entries` | integer | Count of fills with `reason` = `ENTRY` (always 0 or 2). |
| `num_rolls` | integer | Count of strike-change events (= count of `ROLL` fills ÷ 4). |
| `num_squareoffs` | integer | Count of fills with `reason` = `SQUAREOFF` (always 0 or 2). |
| `gross_pnl` | float | End-of-day total PnL for this underlier (= `*_realized_pnl` at `15:29:59` from D5, since unrealized is zero at EOD). |
| `first_entry_time` | `HH:MM:SS` or null | Timestamp of the first `ENTRY` fill. Null if no entry occurred (per A20). |
| `last_roll_time` | `HH:MM:SS` or null | Timestamp of the last `ROLL` fill. Null if no rolls occurred. |
| `num_unique_strikes_held` | integer | Count of distinct strikes held during the day. Justification: natural measure of intraday churn — a day with 1 unique strike means no rolls; higher values indicate frequent strike switching. Derivable from D4. |
| `max_favorable_excursion` | float | Peak intraday `*_total_pnl` for this underlier (maximum of the per-second PnL series from D5). Justification: shows how much the strategy gained at its best point before settling to EOD PnL; natural complement to `gross_pnl` for assessing intraday behavior. |
| `max_adverse_excursion` | float | Trough intraday `*_total_pnl` for this underlier (minimum of the per-second PnL series from D5). Justification: reveals worst-case intraday drawdown; critical for understanding risk characteristics of the strategy. |

**Sort order:** `trade_date` ASC, `underlier` ASC.

**Justification for additional columns beyond the minimum five (date, underlier, num_trades, num_rolls, gross_pnl):**

- `num_entries`, `num_squareoffs`: Complete the trade-count decomposition. Together with `num_rolls`, the identity `num_trades = num_entries + (4 × num_rolls) + num_squareoffs` serves as a built-in integrity check against D3.
- `first_entry_time`, `last_roll_time`: Trivially derivable from D3 and immediately answer "when did the strategy become active" and "when was the last rebalance" without requiring the reader to query D3.
- `num_unique_strikes_held`: Direct measure of churn, answering the findings question "how often did the strategy roll" at daily granularity.
- `max_favorable_excursion`, `max_adverse_excursion`: Standard intraday risk metrics derivable from D5, answering "whether PnL was dominated by a few extreme intraday moves."

---

## §3 — Chart Definitions

### D7 — Cumulative PnL Plot

**Source data:** D5 (`mtm_timeline.csv`).

**What to plot:** Three line series on a single chart.

| Element | Definition |
|---|---|
| **X-axis** | `timestamp` (continuous across all 21 trading days; non-trading gaps between days may be collapsed or left as gaps — either is acceptable). |
| **Y-axis** | Cumulative total PnL in the same units as the price data (INR notional per unit). |
| **Series 1** | `nifty_total_pnl`, carried forward across days (day N starts where day N−1 ended). Label: `NIFTY`. |
| **Series 2** | `banknifty_total_pnl`, carried forward across days. Label: `BANKNIFTY`. |
| **Series 3** | `combined_total_pnl`, carried forward across days. Label: `Combined`. |

**Cross-day accumulation:** Within D5, PnL resets each day (realized PnL starts at zero). For this chart, the plotting code must compute a running cross-day cumulative sum: `cumulative_pnl[day N] = cumulative_pnl[day N−1 EOD] + intraday_pnl[day N]`.

**Format:** Static image (PNG or PDF). Must include axis labels, legend, and a title.

---

### D8 — Daily PnL Plot

**Source data:** D6 (`daily_summary.csv`).

**What to plot:** A grouped bar chart.

| Element | Definition |
|---|---|
| **X-axis** | `trade_date` (one tick per trading day, 21 ticks total). |
| **Y-axis** | `gross_pnl` (end-of-day realized PnL in INR notional per unit). |
| **Bar group per date** | Three bars: NIFTY (from the NIFTY row), BANKNIFTY (from the BANKNIFTY row), and Combined (sum of both). |

**Format:** Static image (PNG or PDF). Must include axis labels, legend, and a title. A horizontal zero-line must be visible for reference.

---

## §4 — Findings Section (D9)

**Location:** Included as a dedicated section within D2 (README.md), titled "Key Findings."

**Required content:** The findings section must answer the following questions explicitly, with supporting numbers. Each answer must be a concise bullet point or short paragraph — not a multi-page analysis.

### Mandatory bullet points:

1. **Total trades executed** — across the full backtest, per underlier and combined. Cross-check: must match the row count of D3.
2. **Total rolls executed** — per underlier and combined. A single roll = one strike-change event (4 fills per A17).
3. **Total end-of-month PnL** — per underlier and combined. Must match the final cumulative value in D7.
4. **Average daily PnL** — per underlier and combined (= total PnL ÷ 21).
5. **Best and worst trading days** — by `gross_pnl`, per underlier and combined. State the date and PnL value.
6. **Average rolls per day** — per underlier. Indicates how frequently the closest strike changed.
7. **Which underlier had higher turnover** — measured by total roll count. State both counts.
8. **Whether PnL was dominated by a few days** — qualitative observation: was the distribution of daily PnL roughly even, or did 2–3 days account for most of the total?
9. **Intraday churn observation** — based on `num_unique_strikes_held` from D6: did the strategy frequently switch strikes, or was it relatively stable within a day?
10. **Data quality issues encountered** — list any empty files, corrupt files, missing CE/PE pairs, or days where the strategy was flat due to data issues (per A15, A20). If none, state "No data quality issues encountered."

### Optional (encouraged but not mandatory):

- Observation on whether CE or PE legs contributed more to PnL (derivable from D3 and D5).
- Observation on peak intraday drawdown across all days (from `max_adverse_excursion` in D6).
- Any other pattern noticed during validation that a reviewer should be aware of.

---

## §5 — Source Code Requirements (D1)

| Requirement | Detail |
|---|---|
| **Runnable** | The code must execute end-to-end from raw data in `Data/allData/` to produce D3–D8 without manual intervention. |
| **Reproducible** | Running the code twice on the same data must produce identical outputs. |
| **No hardcoded absolute paths** | File paths must be relative or configurable. |
| **Dependencies documented** | A `requirements.txt` (Python) or equivalent must list all dependencies with versions. |
| **Single entry point** | One clearly documented command or script to run the full backtest (e.g. `python run_backtest.py`). |

---

## §6 — README Requirements (D2)

The README.md must contain the following sections in order:

1. **Assignment Objective** — one-paragraph summary of what this project does.
2. **Dataset Structure** — brief description of the data layout (may reference SPEC.md §2).
3. **Strategy Rules** — concise restatement of the 11 rules (may reference SPEC.md §3).
4. **Assumptions** — list of key assumptions or a reference to ASSUMPTIONS.md.
5. **How to Run** — exact commands to execute the backtest from a clean environment.
6. **Output Files** — table listing each output file (D3–D8) with a one-line description.
7. **Key Findings** — the D9 findings section (see §4 above).
8. **Limitations** — known limitations of the base version (e.g. no transaction costs, no slippage, idealized execution).

---

## §7 — Out of Scope for Base Deliverables

The following are explicitly NOT required in the minimum submission package:

1. Interactive dashboards, web UIs, or Jupyter notebook visualizations.
2. Additional strategy variants beyond the closest-strike long straddle.
3. Slippage models, transaction cost models, or execution realism of any kind (per A10, A11).
4. Per-trade attribution beyond the fields defined in the `trades.csv` schema (e.g. no Greeks, no implied volatility, no delta/gamma decomposition).
5. Intraday MTM charts for individual days (only the two aggregate charts D7 and D8 are required).
6. Statistical risk metrics (Sharpe ratio, Sortino ratio, VaR, etc.).
7. Multi-month or multi-year backtesting.
8. Configuration files or parameterized strategy inputs.
9. Automated testing suites (unit tests, integration tests).
10. CI/CD pipelines, Docker containers, or deployment artifacts.
11. Roll-frequency histograms, holding-duration distributions, or PnL-by-weekday breakdowns.
12. Comparison reports across multiple strategies.

---

## §8 — Future Creative Extensions (Not Required for Base Submission)

The following categories are recognized as valuable enhancements but are explicitly excluded from the base deliverable scope. They may be pursued only after all items in §1 are complete, correct, and verified.

- **Additional strategy variants** — e.g. rebalance only when strike changes by more than one step, time-window-restricted trading, single-leg strategies.
- **Execution realism** — slippage modeling, fixed/proportional transaction costs, delayed fills, stale-quote rejection.
- **Richer analytics** — drawdown curves, holding-duration histograms, PnL attribution by CE vs PE leg, roll-frequency analysis, PnL by weekday.
- **Interactive visualizations** — HTML dashboards, interactive notebooks, per-day intraday replay charts, annotated trade overlays on price charts.
- **Configuration-driven parameters** — externalized strategy config for evaluation frequency, entry start time, exit cutoff time, tie-break rule, cost model selection.
- **Strategy comparison framework** — side-by-side reporting for multiple strategy variants on the same dataset.
- **Presentation polish** — styled HTML reports, branded charts, executive summary documents.

---

*End of deliverables document.*
