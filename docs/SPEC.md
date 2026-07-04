# SPEC.md — Strategy Specification (Base Version)

**Status:** DRAFT — Requires sign-off on all items in §4 before implementation begins.
**Scope:** Closest-strike long straddle, intraday, NIFTY + BANKNIFTY, November 2022.

---

## §1 — Definitions

| Term | Meaning |
|---|---|
| **Trading day** | A single dated folder in `Data/allData/` (e.g. `NSE_20221101`). The dataset contains 21 such folders covering November 2022. |
| **Session window** | 09:15:00 through 15:30:00 inclusive, at 1-second resolution. |
| **Underlier** | One of exactly two symbols: `NIFTY` or `BANKNIFTY`. |
| **Futures price** | The `Price` column value from the `-I.csv` continuous futures file for the relevant underlier. |
| **Nearest expiry** | The earliest option expiry date, parsed from option filenames, that is ≥ the current trading date. |
| **Closest strike** | The strike price (from available nearest-expiry option contracts) with the minimum absolute distance to the current futures price. |
| **Target position** | The pair of instruments the strategy demands to be held at a given second: 1 unit long of closest-strike CE + 1 unit long of closest-strike PE. |
| **Roll** | Simultaneous exit of both legs at the old strike and entry of both legs at the new strike. |
| **Forced square-off** | Closing all open positions at end of day, regardless of any other condition. |
| **Tick** | A single row in any CSV file, representing one traded event with columns: Date, Time, Price, Volume, Open Interest. Files have no header row. |
| **1-second grid** | A uniform time series from session start to session end with exactly one state per second per instrument. |

---

## §2 — Data Layout

### 2.1 — Directory structure

```
Data/allData/
  NSE_YYYYMMDD/
    Futures (Continuous)/
      NIFTY-I.csv
      NIFTY-II.csv
      NIFTY-III.csv
      BANKNIFTY-I.csv
      BANKNIFTY-II.csv
      BANKNIFTY-III.csv
      FINNIFTY-I.csv
      FINNIFTY-II.csv
      FINNIFTY-III.csv
    Options/
      {UNDERLIER}{YYMMDD_EXPIRY}{STRIKE}{CE|PE}.csv
```

### 2.2 — CSV schema (all files)

Five columns, no header row, comma-separated:

| Position | Name | Format | Example |
|---|---|---|---|
| 1 | Date | `YYYYMMDD` | `20221101` |
| 2 | Time | `HH:MM:SS` | `09:15:00` |
| 3 | Price | Decimal | `18161.10` |
| 4 | Volume | Integer | `6000` |
| 5 | Open Interest | Integer | `11713150` |

Multiple rows may share the same Date+Time (multiple ticks within the same second).

### 2.3 — Option filename encoding

Pattern: `{UNDERLIER}{YYMMDD}{STRIKE}{CE|PE}.csv`

Example: `NIFTY22110317300CE.csv` → Underlier=NIFTY, Expiry=2022-11-03, Strike=17300, Type=CE.

Example: `BANKNIFTY22110341500PE.csv` → Underlier=BANKNIFTY, Expiry=2022-11-03, Strike=41500, Type=PE.

The dataset also contains files for FINNIFTY and MIDCPNIFTY. These are excluded per Rule 3.

---

## §3 — Strategy Rules

### Rule 1 — Dataset boundary

The system SHALL process exactly the data located under `Data/allData/`. All 21 dated folders in that directory constitute the backtest universe. No external data sources are used.

**Out of scope:** Fetching, generating, or referencing any market data beyond what exists in `Data/allData/`.

---

### Rule 2 — Date-by-date processing

Each dated folder (e.g. `NSE_20221101`) SHALL be processed independently. No state carries over between trading days. Each day is a self-contained simulation.

**Out of scope:** Multi-day position carry, overnight risk calculation, cross-day state persistence.

---

### Rule 3 — Underlier restriction

The system SHALL trade only `NIFTY` and `BANKNIFTY`. All files belonging to `FINNIFTY`, `MIDCPNIFTY`, or any other underlier present in the dataset SHALL be ignored entirely — not loaded, not parsed, not referenced.

**Out of scope:** Trading, referencing, or loading FINNIFTY, MIDCPNIFTY, or any underlier other than NIFTY and BANKNIFTY.

---

### Rule 4 — Futures price source

For each underlier, the futures reference price SHALL be sourced exclusively from the `-I.csv` file in the `Futures (Continuous)/` subfolder (i.e. `NIFTY-I.csv` and `BANKNIFTY-I.csv`).

**Out of scope:** Reading, referencing, or using `-II.csv`, `-III.csv`, or any FINNIFTY/MIDCPNIFTY futures files for any purpose.

---

### Rule 5 — Nearest-expiry option selection

For each underlier on each trading day, the system SHALL determine the nearest expiry by parsing expiry dates from option filenames and selecting the earliest expiry date that is ≥ the current trading date. Only option contracts matching that nearest expiry SHALL be considered tradable for that underlier on that day.

**Out of scope:** Trading or referencing options from non-nearest expiries (i.e. second-nearest, third-nearest, or any farther-dated contracts).

---

### Rule 6 — Maximum position size

The maximum position held in any single instrument at any point in time SHALL be exactly 1 unit. No scaling, no pyramiding, no multiple lots.

**Out of scope:** Variable position sizing, lot-size multiples, scaling into or out of positions.

---

### Rule 7 — Evaluation frequency

The strategy SHALL evaluate state serially at every second of the trading session, from session start to session end. The evaluation timeline is a uniform 1-second grid.

**Out of scope:** Sub-second evaluation, tick-by-tick evaluation, evaluation at frequencies coarser than 1 second.

---

### Rule 8 — Target position definition

At every evaluated second, the target position for each underlier SHALL be:

- Long 1 unit of the CE option at the strike closest to the current futures price.
- Long 1 unit of the PE option at the strike closest to the current futures price, at the same strike as the CE.

Both legs SHALL always share the same strike. The target position is always a straddle — never a single leg, never a strangle.

**Out of scope:** Strangles, directional trades, short positions, delta-hedged positions, positions at strikes other than the closest strike.

---

### Rule 9 — Roll mechanics

Whenever the closest strike changes from one evaluated second to the next, both the CE and PE legs SHALL be rolled together as an atomic operation:

1. Exit the CE at the old strike.
2. Exit the PE at the old strike.
3. Enter the CE at the new strike.
4. Enter the PE at the new strike.

Partial rolls (rolling only one leg while keeping the other) are prohibited. If the closest strike does not change, no action is taken.

**Out of scope:** Partial rolls, staggered rolls, roll-delay logic, hysteresis or deadband around strike changes.

---

### Rule 10 — End-of-day forced square-off

At the end of every trading day, all open positions SHALL be closed unconditionally. This applies regardless of whether the strategy would otherwise remain in the position.

**Out of scope:** Holding positions past session end, overnight carry, early forced exit before session end (other than normal roll logic).

---

### Rule 11 — Required outputs

The system SHALL produce:

1. **Mark-to-market PnL over time:** A time-indexed series showing cumulative and/or running PnL at each evaluated second.
2. **Position record:** A record of which instruments are held at any point in time, including entry timestamps and prices.

**Out of scope (for the base version):** Interactive dashboards, live-streaming outputs, per-trade analytics beyond what is needed for the above two outputs.

---

## §4 — Open Assumptions Requiring Sign-Off

The original 11 rules are silent on the items below. Each item lists a proposed default. **No default is final until explicitly approved.** Implementation SHALL NOT begin until all items in this section are resolved.

---

### A1 — Trading session boundaries

**Question:** What are the exact start and end timestamps of the 1-second evaluation grid?

**Observed in data:** Tick data begins at `09:15:00` and ends at `15:30:00`.

**Proposed default:** The 1-second grid runs from `09:15:00` to `15:29:59` inclusive (a total of 22,500 seconds). The forced square-off under Rule 10 occurs at `15:29:59` (the last evaluated second). The timestamp `15:30:00` is not evaluated as a strategy second but MAY be used as a price source for the square-off fill if it is the latest available tick.

---

### A2 — Multiple ticks within the same second

**Question:** When multiple ticks exist within the same second for a single instrument, which price represents that second on the 1-second grid?

**Proposed default:** Use the **last tick** (the tick appearing latest in the file for that second) as the representative price for that second. This is equivalent to a "last-traded-price" convention.

---

### A3 — Forward-filling missing seconds

**Question:** Not every instrument has a tick at every second. How are gaps handled on the 1-second grid?

**Proposed default:** Forward-fill the last known price. If an instrument has a tick at `09:15:03` and the next tick at `09:15:07`, then seconds `09:15:04`, `09:15:05`, and `09:15:06` all carry the price from the `09:15:03` tick. An instrument has no price on the grid until its first tick of the day.

---

### A4 — Pre-first-tick period

**Question:** What happens in the seconds between session start and the first tick for a given instrument?

**Proposed default:** The instrument has **no valid price** during this period. It is treated as unavailable. The strategy cannot enter a position in an instrument with no valid price (see A5).

---

### A5 — Entry conditions when price data is missing

**Question:** At a given second, the strategy wants to hold a straddle at strike K, but one or both of the CE/PE at strike K have no valid price yet (no tick has arrived). What happens?

**Proposed default:** The strategy SHALL NOT enter the straddle at that strike until **both** the CE and PE at that strike have valid (forward-filled) prices on the 1-second grid. Until then, the target position for that underlier at that second is flat (zero holdings). If the system is already holding a straddle from a previous second and the new closest strike's CE or PE has no valid price, the old straddle SHALL be exited but the new straddle SHALL NOT be entered until both legs have valid prices.

---

### A6 — Closest-strike tie-breaking

**Question:** If two strikes are equidistant from the current futures price, which one is selected?

**Proposed default:** Choose the **lower strike**. This is a deterministic, arbitrary convention. Example: futures at 18100, strikes at 18050 and 18150 are both 50 points away → select 18050.

---

### A7 — Eligible-strike definition (both legs required)

**Question:** Must a strike have both a CE file and a PE file present in the dataset to be considered a valid candidate for closest-strike selection?

**Proposed default:** Yes. A strike is eligible for selection ONLY if both `{UNDERLIER}{EXPIRY}{STRIKE}CE.csv` and `{UNDERLIER}{EXPIRY}{STRIKE}PE.csv` exist in the `Options/` folder for that day. Strikes with only one side present are excluded from the closest-strike search entirely.

---

### A8 — Execution price convention

**Question:** When the strategy enters or exits a position, what price is used for the fill?

**Proposed default:** The fill price is the **current marked price** on the 1-second grid for that instrument at that second. This is the forward-filled last-traded-price as defined in A2/A3. No bid-ask spread modeling, no slippage, no execution delay.

---

### A9 — Mark-to-market pricing convention

**Question:** How is unrealized PnL calculated for open positions at each evaluated second?

**Proposed default:** Unrealized PnL for a position = (current marked price on the 1-second grid − entry price) × position size (which is always 1). If the marked price for an open instrument becomes unavailable (no tick ever arrived, which should not happen for a held instrument under A5), the last known marked price is carried forward.

---

### A10 — Transaction costs

**Question:** Are brokerage, STT, stamp duty, GST, exchange fees, or any other transaction costs applied?

**Proposed default:** No. The base version applies **zero transaction costs** of any kind. All fills are frictionless.

---

### A11 — Slippage and latency

**Question:** Is any slippage or execution latency modeled?

**Proposed default:** No. Fills are assumed to occur instantaneously at the marked price. No slippage, no market impact, no latency.

---

### A12 — NIFTY vs BANKNIFTY independence

**Question:** Are NIFTY and BANKNIFTY positions managed independently or as a combined portfolio?

**Proposed default:** Independently. Each underlier has its own position state, its own closest-strike calculation, and its own PnL stream. A combined portfolio-level PnL is computed by summing the two independent streams. No cross-underlier logic exists.

---

### A13 — Roll event at the same second as entry

**Question:** If at the very first evaluated second where both legs have valid prices, the closest strike differs from a "no previous strike" state — is this treated as a roll (exit + enter) or just an initial entry?

**Proposed default:** This is treated as an **initial entry only** (there is nothing to exit). A roll event is logged only when there is a prior held strike that differs from the new closest strike.

---

### A14 — Forced square-off price

**Question:** What price is used for the end-of-day forced square-off?

**Proposed default:** The marked price on the 1-second grid at the last evaluated second (proposed as `15:29:59` per A1). If the last evaluated second's marked price is forward-filled from an earlier tick, that forward-filled price is used.

---

### A15 — Handling of empty or corrupt files

**Question:** What happens if a CSV file is empty, contains only whitespace, or has malformed rows?

**Proposed default:** An empty or corrupt file is treated as if the file does not exist. If this causes a strike to lose one of its legs, that strike becomes ineligible per A7. If both the CE and PE are missing or corrupt, that strike is simply not available. No error is raised; the system logs the occurrence and continues.

---

### A16 — PnL granularity in outputs

**Question:** Should the MTM PnL output be per-underlier, combined, or both?

**Proposed default:** Both. The output SHALL include per-underlier PnL columns AND a combined total column at every evaluated second.

---

### A17 — Roll event definition for logging

**Question:** What constitutes a "trade" or "event" in the output record? Is a roll one event or four (2 exits + 2 entries)?

**Proposed default:** Each individual fill is a separate trade record. A roll therefore produces 4 trade records (exit CE, exit PE, enter CE, enter PE), all sharing the same timestamp. An initial entry produces 2 records. A forced square-off produces 2 records. Each record includes: timestamp, underlier, instrument, direction (BUY/SELL), price, quantity (always 1), and reason (ENTRY, ROLL, SQUAREOFF).

---

### A18 — Strike spacing awareness

**Question:** NIFTY options have 50-point strike spacing. BANKNIFTY options have 100-point strike spacing. Does the system need to know or enforce these conventions?

**Proposed default:** No. The system discovers available strikes from the filenames present in the dataset. It does not assume or enforce any fixed strike spacing. Whatever strikes exist in the data are the universe.

---

### A19 — Duplicate-timestamp handling within a file

**Question:** A CSV file may contain multiple rows with identical Date+Time. Beyond the "last tick wins" rule in A2, is any additional deduplication needed?

**Proposed default:** No additional deduplication. Rows with the same timestamp are processed in file order; the last row for that timestamp becomes the representative price per A2. No rows are discarded during loading — the overwrite happens naturally during grid construction.

---

### A20 — What constitutes "no valid strike exists"

**Question:** If on a given day and underlier, no strike has both a CE and PE file present for the nearest expiry, what happens?

**Proposed default:** The strategy holds a flat position for that underlier for the entire day. No error is raised. The day is logged as having zero trades for that underlier.

---

## §5 — Boundary Conditions Summary

| Scenario | Behavior |
|---|---|
| First second of the day, no ticks yet for any option | Strategy holds flat. No entry. |
| CE has a price, PE does not, at the closest strike | Strategy holds flat. No entry at that strike. |
| Closest strike changes but new strike's PE has no price yet | Exit old straddle. Do NOT enter new straddle. Hold flat until both legs available. |
| Futures price has no tick at a given second | Forward-fill from the last futures tick. If no futures tick has arrived yet, closest-strike calculation cannot run; hold flat. |
| Two strikes equidistant from futures | Select the lower strike. |
| Closest strike is the same as the previous second | No action. Hold existing position. |
| Last second of the day | Execute forced square-off at the marked price on the grid. |
| File is empty or corrupt | Treat as non-existent. Strike may lose eligibility. |
| No eligible strike exists for the entire day | Flat all day. Zero trades. Log the condition. |

---

## §6 — What This Document Does NOT Cover

The following are explicitly deferred to a later phase and SHALL NOT be addressed during base implementation:

1. Code structure, file architecture, class design, or module layout.
2. Choice of programming language, frameworks, or libraries.
3. Performance optimization or parallelization strategy.
4. Visualization, charting, or dashboard design.
5. Transaction cost models, slippage models, or execution realism.
6. Alternative strategies, parameterization, or strategy configuration.
7. Statistical analysis, risk metrics, or attribution beyond raw PnL.
8. Deployment, CI/CD, or packaging.

---

*End of specification.*
