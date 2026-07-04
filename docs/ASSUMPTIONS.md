# ASSUMPTIONS.md — Finalized Assumptions for Base Implementation

**Status:** FINAL — Approved and binding.
**Effective date:** 2026-07-01
**Governing specification:** SPEC.md §4

All assumptions in this document are final and binding for the base implementation. Any future change requires updating this document explicitly, with a version note appended at the bottom.

---

## Policy Alignment Record

Before approval, each assumption (A1–A20) was verified against the following 6 non-negotiable policies. All 20 assumptions were found to be fully consistent with all 6 policies. No conflicts, weakened wording, or strengthened wording were detected.

| # | Policy | Covered by |
|---|---|---|
| P1 | Intraday timestamps are aligned to a 1-second grid using forward-fill from the latest available tick. | A2, A3, A4 |
| P2 | Entry and exit happen at the latest available option price at that second. | A8 |
| P3 | If both CE and PE prices are not available, skip entry until both become available. | A5 |
| P4 | End-of-day close uses the last available marked price for the open instruments. | A14 |
| P5 | No brokerage, slippage, taxes, or latency in the base version. | A10, A11 |
| P6 | Tie-breaking for closest strike is deterministic, choosing the lower strike first. | A6 |

---

## NEEDS MY DECISION

_None. All 20 assumptions passed policy alignment without conflict._

---

## Approved Assumptions

---

### A1 — Trading session boundaries · APPROVED

**Question:** What are the exact start and end timestamps of the 1-second evaluation grid?

**Final decision:** The 1-second grid runs from `09:15:00` to `15:29:59` inclusive (a total of 22,500 seconds). The forced square-off under Rule 10 occurs at `15:29:59` (the last evaluated second). The timestamp `15:30:00` is not evaluated as a strategy second but MAY be used as a price source for the square-off fill if it is the latest available tick.

**Implication:** The evaluation loop iterates exactly 22,500 times per day. Square-off logic fires at the final iteration. Tick data at `15:30:00` is loaded but only used for forward-fill/mark, not as an evaluation second.

---

### A2 — Multiple ticks within the same second · APPROVED

**Question:** When multiple ticks exist within the same second for a single instrument, which price represents that second on the 1-second grid?

**Final decision:** Use the **last tick** (the tick appearing latest in file order for that second) as the representative price for that second. This is equivalent to a "last-traded-price" convention.

**Implication:** Within any CSV file, rows are processed in file order. For a given Date+Time, only the last row's Price value survives onto the 1-second grid. Earlier rows for the same second are overwritten, not discarded during loading.

---

### A3 — Forward-filling missing seconds · APPROVED

**Question:** Not every instrument has a tick at every second. How are gaps handled on the 1-second grid?

**Final decision:** Forward-fill the last known price. If an instrument has a tick at `09:15:03` and the next tick at `09:15:07`, then seconds `09:15:04`, `09:15:05`, and `09:15:06` all carry the price from the `09:15:03` tick. An instrument has no price on the grid until its first tick of the day.

**Implication:** The 1-second grid for any instrument starts as empty (NaN/null) and is only populated from the first tick onward. The forward-fill operation never backfills prior to the first tick.

---

### A4 — Pre-first-tick period · APPROVED

**Question:** What happens in the seconds between session start and the first tick for a given instrument?

**Final decision:** The instrument has **no valid price** during this period. It is treated as unavailable. The strategy cannot enter a position in an instrument with no valid price (see A5).

**Implication:** A late-opening instrument (e.g., an illiquid deep OTM option whose first tick arrives at 09:20:00) is invisible to the strategy for the first 300 seconds of the day.

---

### A5 — Entry conditions when price data is missing · APPROVED

**Question:** At a given second, the strategy wants to hold a straddle at strike K, but one or both of the CE/PE at strike K have no valid price yet (no tick has arrived). What happens?

**Final decision:** The strategy SHALL NOT enter the straddle at that strike until **both** the CE and PE at that strike have valid (forward-filled) prices on the 1-second grid. Until then, the target position for that underlier at that second is flat (zero holdings). If the system is already holding a straddle from a previous second and the new closest strike's CE or PE has no valid price, the old straddle SHALL be exited but the new straddle SHALL NOT be entered until both legs have valid prices.

**Implication:** There may be seconds where the strategy is flat despite a valid closest strike existing, purely because one leg lacks price data. This is intentional — entering a straddle blind on one leg would produce meaningless PnL.

---

### A6 — Closest-strike tie-breaking · APPROVED

**Question:** If two strikes are equidistant from the current futures price, which one is selected?

**Final decision:** Choose the **lower strike**. This is a deterministic, arbitrary convention. Example: futures at 18100, strikes at 18050 and 18150 are both 50 points away → select 18050.

**Implication:** The closest-strike selection function must sort candidates by absolute distance first, then by strike value ascending to break ties. The result is always a single, unambiguous strike.

---

### A7 — Eligible-strike definition (both legs required) · APPROVED

**Question:** Must a strike have both a CE file and a PE file present in the dataset to be considered a valid candidate for closest-strike selection?

**Final decision:** Yes. A strike is eligible for selection ONLY if both `{UNDERLIER}{EXPIRY}{STRIKE}CE.csv` and `{UNDERLIER}{EXPIRY}{STRIKE}PE.csv` exist in the `Options/` folder for that day. Strikes with only one side present are excluded from the closest-strike search entirely.

**Implication:** The eligible-strike set is determined at file-discovery time (once per day per underlier), not at runtime. This is a structural filter, separate from the runtime price-availability check in A5.

---

### A8 — Execution price convention · APPROVED

**Question:** When the strategy enters or exits a position, what price is used for the fill?

**Final decision:** The fill price is the **current marked price** on the 1-second grid for that instrument at that second. This is the forward-filled last-traded-price as defined in A2/A3. No bid-ask spread modeling, no slippage, no execution delay.

**Implication:** Every fill is at the mid/last price. Realized PnL is computed as exit price minus entry price. There is no distinction between "theoretical" and "executable" price in the base version.

---

### A9 — Mark-to-market pricing convention · APPROVED

**Question:** How is unrealized PnL calculated for open positions at each evaluated second?

**Final decision:** Unrealized PnL for a position = (current marked price on the 1-second grid − entry price) × position size (which is always 1). If the marked price for an open instrument becomes unavailable (no tick ever arrived, which should not happen for a held instrument under A5), the last known marked price is carried forward.

**Implication:** The MTM series reflects continuous mark-to-market using the same price source as the execution model. No separate "fair value" or "model price" is used.

---

### A10 — Transaction costs · APPROVED

**Question:** Are brokerage, STT, stamp duty, GST, exchange fees, or any other transaction costs applied?

**Final decision:** No. The base version applies **zero transaction costs** of any kind. All fills are frictionless.

**Implication:** PnL is gross of all costs. Any comparison to real-world performance must account for the absence of transaction costs in this version.

---

### A11 — Slippage and latency · APPROVED

**Question:** Is any slippage or execution latency modeled?

**Final decision:** No. Fills are assumed to occur instantaneously at the marked price. No slippage, no market impact, no latency.

**Implication:** The strategy observes a price and fills at that exact price in the same second. This is an idealized execution model suitable for a base version only.

---

### A12 — NIFTY vs BANKNIFTY independence · APPROVED

**Question:** Are NIFTY and BANKNIFTY positions managed independently or as a combined portfolio?

**Final decision:** Independently. Each underlier has its own position state, its own closest-strike calculation, and its own PnL stream. A combined portfolio-level PnL is computed by summing the two independent streams. No cross-underlier logic exists.

**Implication:** The engine can be thought of as running two parallel, non-interacting strategy instances — one for NIFTY, one for BANKNIFTY — sharing only the calendar of trading days.

---

### A13 — Roll event at the same second as entry · APPROVED

**Question:** If at the very first evaluated second where both legs have valid prices, the closest strike differs from a "no previous strike" state — is this treated as a roll (exit + enter) or just an initial entry?

**Final decision:** This is treated as an **initial entry only** (there is nothing to exit). A roll event is logged only when there is a prior held strike that differs from the new closest strike.

**Implication:** The trade log for any day's first entry will show reason=ENTRY, not reason=ROLL. Roll count metrics start from zero at the beginning of each day.

---

### A14 — Forced square-off price · APPROVED

**Question:** What price is used for the end-of-day forced square-off?

**Final decision:** The marked price on the 1-second grid at the last evaluated second (defined as `15:29:59` per A1). If the last evaluated second's marked price is forward-filled from an earlier tick, that forward-filled price is used.

**Implication:** The square-off price is the best available price at session end, even if stale. This is consistent with the overall forward-fill convention and avoids special-casing the final second.

---

### A15 — Handling of empty or corrupt files · APPROVED

**Question:** What happens if a CSV file is empty, contains only whitespace, or has malformed rows?

**Final decision:** An empty or corrupt file is treated as if the file does not exist. If this causes a strike to lose one of its legs, that strike becomes ineligible per A7. If both the CE and PE are missing or corrupt, that strike is simply not available. No error is raised; the system logs the occurrence and continues.

**Implication:** The system must be resilient to bad data. A validation pass at load time should flag these files for logging but not halt execution.

---

### A16 — PnL granularity in outputs · APPROVED

**Question:** Should the MTM PnL output be per-underlier, combined, or both?

**Final decision:** Both. The output SHALL include per-underlier PnL columns AND a combined total column at every evaluated second.

**Implication:** The MTM output has at minimum three PnL columns per row: NIFTY PnL, BANKNIFTY PnL, and Total PnL.

---

### A17 — Roll event definition for logging · APPROVED

**Question:** What constitutes a "trade" or "event" in the output record? Is a roll one event or four (2 exits + 2 entries)?

**Final decision:** Each individual fill is a separate trade record. A roll therefore produces 4 trade records (exit CE, exit PE, enter CE, enter PE), all sharing the same timestamp. An initial entry produces 2 records. A forced square-off produces 2 records. Each record includes: timestamp, underlier, instrument, direction (BUY/SELL), price, quantity (always 1), and reason (ENTRY, ROLL, SQUAREOFF).

**Implication:** Trade log row count = (2 × number of initial entries) + (4 × number of rolls) + (2 × number of square-offs) per underlier per day. Each row is atomic and self-describing.

---

### A18 — Strike spacing awareness · APPROVED

**Question:** NIFTY options have 50-point strike spacing. BANKNIFTY options have 100-point strike spacing. Does the system need to know or enforce these conventions?

**Final decision:** No. The system discovers available strikes from the filenames present in the dataset. It does not assume or enforce any fixed strike spacing. Whatever strikes exist in the data are the universe.

**Implication:** The system is agnostic to strike intervals. This makes it robust to irregular strike listings and avoids hardcoding exchange-specific conventions.

---

### A19 — Duplicate-timestamp handling within a file · APPROVED

**Question:** A CSV file may contain multiple rows with identical Date+Time. Beyond the "last tick wins" rule in A2, is any additional deduplication needed?

**Final decision:** No additional deduplication. Rows with the same timestamp are processed in file order; the last row for that timestamp becomes the representative price per A2. No rows are discarded during loading — the overwrite happens naturally during grid construction.

**Implication:** The loading pipeline does not need an explicit dedup step. The grid-construction logic inherently resolves duplicates by overwrite order.

---

### A20 — What constitutes "no valid strike exists" · APPROVED

**Question:** If on a given day and underlier, no strike has both a CE and PE file present for the nearest expiry, what happens?

**Final decision:** The strategy holds a flat position for that underlier for the entire day. No error is raised. The day is logged as having zero trades for that underlier.

**Implication:** The system must handle this gracefully as a normal (if unlikely) scenario, not an exception. Output files still include rows for that day — they simply show zero PnL and no trades.

---

## Cross-Reference Index

| Assumption | Primary policy alignment | SPEC.md rule dependency |
|---|---|---|
| A1 | — | Rule 7 (1-second resolution), Rule 10 (EOD close) |
| A2 | P1 (forward-fill from latest tick) | Rule 7 |
| A3 | P1 (forward-fill from latest tick) | Rule 7 |
| A4 | P1 (forward-fill from latest tick) | Rule 7, Rule 8 |
| A5 | P3 (skip if both not available) | Rule 8, Rule 9 |
| A6 | P6 (lower strike tie-break) | Rule 8 |
| A7 | P3 (both legs required) | Rule 8 |
| A8 | P2 (latest available price) | Rule 8, Rule 9 |
| A9 | P2 (latest available price) | Rule 11 |
| A10 | P5 (no costs) | — |
| A11 | P5 (no costs) | — |
| A12 | — | Rule 3 |
| A13 | — | Rule 8, Rule 9 |
| A14 | P4 (last marked price for EOD) | Rule 10 |
| A15 | — | Rule 4, Rule 5 |
| A16 | — | Rule 11 |
| A17 | — | Rule 11 |
| A18 | — | Rule 5 |
| A19 | P1 (latest tick) | Rule 7 |
| A20 | — | Rule 5, Rule 8 |

---

*End of assumptions document.*
