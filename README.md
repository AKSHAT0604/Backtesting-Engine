# NSE Options Intraday Backtesting Engine — Project Report

**Live dashboard:** _[insert your Streamlit Community Cloud URL here]_
**Repository:** this repo · **Assignment:** intraday closest-strike options straddle backtest, NIFTY & BANKNIFTY, November 2022

This document is a self-contained report of what was built, how it was built, and
what it found — written so it can be read on its own (no need to run the code or
open the live dashboard) while still linking out to both for anyone who wants to
go deeper.

---

## Contents

1. [The assignment](#1-the-assignment)
2. [Approach — phase by phase](#2-approach--phase-by-phase)
3. [Architecture](#3-architecture)
4. [Results](#4-results)
5. [Pluggable strategies — the bonus comparison](#5-pluggable-strategies--the-bonus-comparison)
6. [Key findings](#6-key-findings)
7. [Assumptions & limitations](#7-assumptions--limitations)
8. [Interactive dashboard](#8-interactive-dashboard)
9. [How to run](#9-how-to-run)
10. [Output files & repository layout](#10-output-files--repository-layout)

---

## 1. The assignment

Build a backtest — not a profitable strategy, a *measurement instrument* — for a
simple intraday options strategy over one month of NSE tick data:

- Trade **NIFTY** and **BANKNIFTY** only, using the nearest-expiry option
  contracts for each trading day.
- At every **1-second** tick of the trading session, find the strike closest to
  the current futures price and hold **1 long CE + 1 long PE** at that strike.
- When the closest strike changes, **roll**: exit both legs at the old strike,
  enter both legs at the new strike.
- **Square off** all positions at the end of every day.
- Produce **mark-to-market PnL over time** and a record of **which instruments
  are held at any point in time**.
- Make the strategy **pluggable** — the engine should not be hard-wired to this
  one strategy.

The raw data is 21 trading-day folders (`NSE_20221101` … `NSE_20221130`), each
with a `Futures (Continuous)/` folder (`{UNDERLIER}-I/II/III.csv`, only `-I`
used) and an `Options/` folder of per-instrument tick files named
`{UNDERLIER}{YYMMDD}{STRIKE}{CE|PE}.csv` — five headerless columns per file:
`Date, Time, Price, Volume, Open Interest`.

---

## 2. Approach — phase by phase

The project was built in the order below, each phase producing a concrete,
inspectable artifact before the next phase depended on it — so a mistake in
expiry selection, say, would surface immediately in `results/nearest_expiry.csv`
rather than silently corrupting the final PnL three phases later.

| Phase | Question answered | Files that do the work | Artifact produced |
|---|---|---|---|
| **0 — Scope lock** | What exactly does "closest strike," "roll," and "square off" mean when the spec is ambiguous (ties, missing prices, session boundaries)? | — (design docs) | `SPEC.md` (11 numbered rules) and `ASSUMPTIONS.md` (20 resolved edge cases, e.g. *A6: tie-break to the lower strike*, *A5: don't enter a leg with no price yet*) |
| **1 — Dataset understanding** | How many trading days, how many option files per day, does the schema hold up everywhere? | `data_cleaning/step_1_1_dataset_inventory.py`, `data_cleaning/step_1_2_parse_filenames.py`, `engine/option_filename_parser.py` | `results/dataset_inventory.csv`, `results/option_metadata.csv` (31,319 filenames parsed, 0 failures) |
| **2 — Market data layer** | Which expiry is "nearest" on each day? Which strikes actually have both a CE and a PE? How do irregular ticks become a uniform 1-second timeline? | `data_cleaning/nearest_expiry_selector.py`, `engine/filtered_option_universe.py`, `engine/futures_loader.py`, `engine/second_grid_builder.py` | `results/nearest_expiry.csv`, `results/filtered_option_universe.csv`, per-day 22,500-row × N-instrument price grids |
| **3 — Instrument selection** | Given a futures price and a set of eligible strikes, which one is "closest," deterministically? | `engine/strike_map.py`, `engine/instrument_selector.py` | `select_strike()` (unit-tested: exact match, tie-break, extremes, NaN) |
| **4 — Strategy layer** | How do we express "buy the closest straddle" without hard-wiring it into the engine? | `engine/strategies/` package (`base.py`, `closest_strike_straddle.py`, …) | A `Strategy` interface: `get_target_positions(timestamp, market_state) -> {instrument: 1}` |
| **5 — Backtest engine** | Given a strategy's *desired* positions, how do we compute the *trades* needed to get there, and the resulting PnL? | `engine/portfolio_state.py`, `engine/execution_engine.py`, `engine/backtest_runner.py` | `trades.csv`, `positions_timeline.csv`, `mtm_timeline.csv` |
| **6 — Validation** | Does it actually work? Manually, on one real day. | `tests/run_debug_day.py`, `tests/test_edge_cases.py` | `results/debug_reconciliation.csv` (hand-checked against raw ticks) + 5 synthetic edge-case tests (missing price, duplicate timestamps, flat day, whipsaw day, already-flat square-off) — all pass |
| **7/8 — Full run & reporting** | What happened across all 21 days, both underliers? | `run_strategy.py`, `engine/reporting.py` | `results/strategies/<key>/*.{csv,parquet}`, `backtest_report.ipynb`, this report |
| **9 — Packaging** | Can a stranger clone this and run it? | repo reorg into `engine/ · data_cleaning/ · tests/ · dashboard/ · docs/`, `engine/data_paths.py` | reproducible from a clean checkout |
| **10 — Creative extensions** | What can be added *on top of* a correct base without touching it? | `engine/strategies/farthest_strike_straddle.py`, `atm_open_hold_straddle.py`, `dashboard/` | 2 bonus strategies, an interactive Streamlit portal |

### How a single second actually gets processed

To make "how did you get this number from the raw data" concrete, here is the
exact chain for one evaluated second, e.g. `2022-11-01 09:15:03` for NIFTY:

1. **`second_grid_builder.py`** has already forward-filled the last known price
   of `NIFTY-I.csv` and every eligible NIFTY option file onto a uniform
   22,500-row (`09:15:00`–`15:29:59`) index for that day, so this second has a
   defined futures price and a defined price for every listed strike (or `NaN`
   if that instrument hasn't ticked yet).
2. **`instrument_selector.select_strike()`** takes that second's futures price
   and the list of eligible strikes (both legs present, per `strike_map.py`)
   and returns the single closest strike, breaking ties to the lower one.
3. **`strategies/closest_strike_straddle.py`** wraps that into a target
   position: `{<strike>CE: 1, <strike>PE: 1}` — but only if *both* legs are
   actually priced this second (`MarketState.pair_if_tradable`); otherwise `{}`.
4. **`execution_engine.py`** diffs that target against the portfolio's current
   holdings. No change → nothing happens. A new strike → SELL the old CE/PE
   fills first, then BUY the new CE/PE, both timestamped to this second.
5. **`portfolio_state.py`** books each fill (realized PnL on a SELL, updated
   entry price on a BUY) and marks every open position to the second's price
   for unrealized PnL.
6. **`backtest_runner.py`** logs the second's `{realized, unrealized, total}`
   PnL into `mtm_timeline.csv`, and — only on a state *change* — appends a row
   to `positions_timeline.csv`.

Repeat 22,500 times a day, 21 days, 2 underliers, and the four output CSVs are
the complete, second-by-second record of the backtest.

---

## 3. Architecture

**The one design decision that mattered most: strategies never touch execution.**
A strategy is a pure function —

```python
def get_target_positions(self, timestamp, market_state) -> dict[str, int]:
    ...
    return {ce_instrument: 1, pe_instrument: 1}   # or {} for flat
```

— that only *declares* what it wants to hold. It cannot read the portfolio, book
a trade, or know what happened last second. `ExecutionEngine` is the only thing
that turns a target into fills, by diffing target vs. current holdings and
emitting SELL-before-BUY. This means the entire accounting/PnL/output layer is
identical no matter which strategy runs — swapping strategies changes *only*
which instruments get targeted each second.

Concretely, **adding a new strategy is one new file**:

```python
# engine/strategies/my_strategy.py
from strategies.base import Strategy, MarketState, register_strategy

@register_strategy(key="my_strategy", name="My Strategy", description="…")
class MyStrategy(Strategy):
    def get_target_positions(self, timestamp, market_state) -> dict[str, int]:
        strike = ...                                    # your selection logic
        return market_state.pair_if_tradable(strike)     # {ce:1, pe:1} or {}
```

Auto-discovery (`engine/strategies/base.py`) picks it up automatically:
`python run_strategy.py --strategy my_strategy` can run it immediately, and the
dashboard's sidebar strategy selector lists it — no other file changes. This
was proven, not just designed: two additional strategies (§5) are running
through the identical engine right now.

### Repository layout

```text
Backtesting-Engine/
  run_strategy.py         # main entry point (run one/all strategies)
  README.md                # this report
  REPORT.md                # flowchart-first companion report
  backtest_report.ipynb   # static matplotlib notebook (superseded by the dashboard)
  engine/                  # every importable module, incl. engine/strategies/
  data_cleaning/           # Phase 1-2 standalone scripts (inventory, parsing, expiry)
  scripts/                 # deployment-prep and report-asset utility scripts
  tests/                   # unit / edge-case / single-day debug harnesses
  redundant/               # superseded or one-off scripts, kept to show the dev process
  docs/                    # SPEC.md, ASSUMPTIONS.md, DELIVERABLES.md, EDGE_CASES.md, report_assets/
  dashboard/               # Streamlit + Plotly analysis portal
  results/                 # generated outputs (+ results/strategies/<key>/)
```

`scripts/` holds the three utilities that run *after* the core backtest: `export_parquet.py` (heavy CSVs → compressed Parquet for deployment), `export_market_data.py` (precomputes the two raw-tick-dependent Day Drilldown charts), and `generate_report_assets.py` (renders the chart images and headline numbers used in §4 below).

`engine/data_paths.py` is the single source of truth for locating `results/`
and the raw dataset, resolved relative to its own file location — this is what
lets every script above sit in its own folder and still run from a clean
checkout, and what lets the dashboard run on Streamlit Cloud where the raw
dataset does not exist at all (§8).

---

## 4. Results

Everything below is the **`closest_strike_straddle`** strategy — the literal
assignment strategy — across all 21 trading days, both underliers. Every
number here is reproducible: `python scripts/generate_report_assets.py` regenerates
both these images and the headline numbers from `results/strategies/closest_strike_straddle/`.

### 4.1 Cumulative mark-to-market PnL

![Cumulative PnL](docs/report_assets/01_cumulative_pnl.png)

**What it shows:** the running total PnL (realized + unrealized) across the
whole month, NIFTY and BANKNIFTY combined.

**How it's derived:** `mtm_timeline.csv` gives realized/unrealized/total PnL
*per second*, but resets to zero at the start of each day (no overnight
position carry, per rule 2). To get a genuine month-long cumulative curve, each
day's series is shifted up by the running total of every prior day's closing
PnL: `cumulative[day N] = cumulative[day N-1, EOD] + intraday[day N]`. The
month closes at **-2,015.30**.

### 4.2 Daily PnL

![Daily PnL](docs/report_assets/02_daily_pnl.png)

**What it shows:** realized+unrealized PnL for each of the 21 days,
independently (not cumulative) — from `daily_summary.csv`'s `gross_pnl` column
summed across both underliers per day.

**How it's derived:** `daily_summary.csv` is built by `engine/reporting.py`
from the *last* row of each day's `mtm_timeline.csv` slice (unrealized PnL is
always exactly 0 there, since the day just squared off — see §7 invariant).
Only **2 of 21 days** closed positive; the rest lost money, mostly by a little.

### 4.3 Roll frequency

![Rolls per day](docs/report_assets/03_rolls_per_day.png)

**What it shows:** how many times per day the closest strike changed (and both
legs were rolled), split by underlier.

**How it's derived:** counted directly from `positions_timeline.csv` rows where
`trigger == "ROLL"` — i.e. a HOLDING state that replaced a *different* prior
HOLDING state (not a fresh entry from flat). Total: **8,131 rolls** across the
month (3,916 NIFTY / 4,215 BANKNIFTY) — an average of **387 rolls/day**,
because the strategy re-evaluates the closest strike every single second and
the futures price constantly ticks across strike boundaries.

### 4.4 Holding-duration distribution

![Holding duration](docs/report_assets/04_holding_duration.png)

**What it shows:** how long each CE+PE pair actually stayed on before the next
roll or the end-of-day close.

**How it's derived:** for each `HOLDING` row in `positions_timeline.csv`, the
duration is the gap to the *next* state-change row for that (day, underlier).
The median holding time is **4 seconds** (NIFTY 3s, BANKNIFTY 5s) — the
strategy is essentially always mid-roll, which is the direct, visible cause of
the modest net loss in §4.2: entering and exiting almost every second pays the
bid/ask-equivalent round-trip on nearly every tick.

### 4.5 CE vs. PE leg attribution

![CE vs PE](docs/report_assets/05_ce_vs_pe.png)

**What it shows:** realized PnL split by option type across the whole month —
CE **-422.30**, PE **-1,593.00**.

**How it's derived:** every fill in `trades.csv` alternates BUY→SELL per
instrument (max position size is 1, per rule 6), so pairing the *i*-th BUY with
the *i*-th SELL for each `(trade_date, instrument_name)` recovers the realized
PnL of every individual closed leg; grouping those by `option_type` gives this
split. (Note: this is a horizontal bar, not a pie — realized PnL here is
signed and both legs are net losers, and a pie chart cannot represent negative
magnitudes. An earlier version of the dashboard used a pie for this and
silently rendered blank; §8 covers the fix.)

### 4.6 NIFTY vs. BANKNIFTY

![NIFTY vs BANKNIFTY](docs/report_assets/06_nifty_vs_banknifty.png)

**What it shows:** the same cross-day cumulative construction as §4.1, kept
separate per underlier instead of combined. BANKNIFTY (**-1,507.45**) drove
roughly 3× the loss of NIFTY (**-507.85**) — consistent with BANKNIFTY's wider
absolute point moves and 100-point strike spacing (vs. NIFTY's 50) causing more
frequent, larger-notional rolls.

### 4.7 Drawdown

![Drawdown](docs/report_assets/07_drawdown.png)

**What it shows:** the running distance below the month's cumulative-PnL peak
so far — i.e. how much the strategy gave back from its best point.

**How it's derived:** `cumulative_pnl - cumulative_pnl.cummax()` on the §4.1
series. Maximum drawdown over the month: **-2,085.30** (slightly worse than the
month's final close, meaning there was a small partial recovery in the last
days).

### 4.8 A single day, in full: 2022-11-01

![Sample day intraday MTM](docs/report_assets/08_sample_day_intraday_mtm.png)

This was the day used for manual reconciliation during validation (Phase 6):
NIFTY PnL (blue), BANKNIFTY PnL (green), and combined (dotted) across the
session, with a sample of that day's 408 roll events marked as thin vertical
lines. The visible step-jumps are rolls; the smoother drift between them is
unrealized mark-to-market on the currently-held pair.

![Futures vs. selected strike](docs/report_assets/09_futures_vs_strike.png)

This is the direct visual proof that the core logic is correct: the dotted
step line (selected strike) tracks the solid futures-price line (blue),
staying at the nearest available strike and jumping to a new one exactly when
the futures price crosses a strike boundary — including the sharp midday dip
around 12:40–13:00 where the strategy chases the price down through several
strikes in quick succession, which is exactly the kind of whipsaw that produces
the negative PnL in §4.2 and §4.4.

---

## 5. Pluggable strategies — the bonus comparison

The assignment explicitly asks for a setup where "different strategies can be
easily plugged in." Two additional strategies were built to prove that claim —
not because they're good ideas, but because they're *different enough* that
sharing the same engine, execution logic, and output schema only works if the
strategy/engine boundary in §3 is real.

| Strategy | Selection rule | Turnover | Month PnL | NIFTY / BANKNIFTY split |
|---|---|---:|---:|---|
| **`closest_strike_straddle`** (the assignment strategy) | Nearest strike to futures, every second | 8,131 rolls, 32,692 fills | **-2,015.30** | -507.85 / -1,507.45 |
| `farthest_strike_straddle` | Farthest *eligible* strike from futures (deep OTM) | 1 roll, 172 fills | **+167.40** | +30.90 / +136.50 |
| `atm_open_hold_straddle` | Lock the ATM strike at the open, hold all day (stateful) | 0 rolls, 168 fills | **-1,696.70** | -246.05 / -1,450.65 |

Every row in that table came from the same `run_strategy.py`, the same
`ExecutionEngine`, the same `mtm_timeline.csv`/`daily_summary.csv` schema — the
only thing that changed between rows is a ~15-line file in
`engine/strategies/`. That is the pluggability requirement, demonstrated rather
than asserted.

(These two are demonstration strategies, not attempts at a better trading
idea — the near-zero-turnover ones simply avoid paying the whipsaw round-trip
that dominates the assignment strategy's losses.)

---

## 6. Key findings

- The assignment strategy rolls **constantly** — a median 3-5 second holding
  time — because the closest strike is recomputed and acted on every single
  second against a continuously ticking futures price.
- **BANKNIFTY** contributed roughly 3× NIFTY's loss and the majority of the
  roll count, consistent with its larger point moves and coarser strike grid.
- With zero transaction costs the strategy still lost money overall
  (**-2,015.30**) — the loss is structural (paying the entry/exit spread on
  near-continuous rolling), not a data or execution artifact, which is
  confirmed by the two dummy strategies: cutting turnover to near-zero (both
  bonus strategies) produces a much smaller loss or a small gain on the exact
  same market data.
- Only 2 of 21 days closed with positive PnL; the month's result is dominated
  by a handful of high-volatility days rather than spread evenly.
- No data-quality issues were encountered: every option filename parsed
  (31,319/31,319), every day had both NIFTY and BANKNIFTY futures files, and
  every trading day ended with all positions squared off exactly once
  (verified programmatically, not just visually — see the invariant checks in
  `tests/`).

---

## 7. Assumptions & limitations

The full, numbered rule set is **[`docs/SPEC.md`](docs/SPEC.md)**; the 20
resolved edge-case decisions are **[`docs/ASSUMPTIONS.md`](docs/ASSUMPTIONS.md)**;
the original day-by-day execution plan this project followed is
**[`docs/backtest-workflow-plan.md`](docs/backtest-workflow-plan.md)**. The
load-bearing assumptions:

- 1-second grid `09:15:00`–`15:29:59` (22,500 seconds/day); last tick per
  second wins; forward-fill; no price exists before an instrument's first tick.
- A strike is tradable only if **both** CE and PE exist *and* both are priced
  this second — otherwise the target is flat.
- Closest-strike ties break to the **lower** strike.
- Fills happen at the marked (forward-filled last-traded) price — **no**
  transaction costs, slippage, spread, or latency.
- NIFTY and BANKNIFTY are managed independently; "combined" PnL is their sum.

**Limitations of the base version, explicitly:**

- **Idealized execution** — real-world costs (brokerage, STT, slippage) would
  make the already-negative closest-strike result meaningfully worse, since it
  trades on nearly every second.
- **Marked-price fills**, not bid/ask — optimistic for a strategy this
  high-turnover.
- **No liquidity/depth model** — a leg is "available" the instant it has any
  tick, regardless of size.
- **Single month, two underliers**, by design (per the assignment).
- **Invariant, verified programmatically:** every one of the 42
  (date, underlier) combinations ends the day `FLAT` via `SQUAREOFF` at exactly
  `15:29:59`, and no instrument-day ever exceeds a position of 1 — both checked
  against every row of every output file, not spot-sampled.

---

## 8. Interactive dashboard

A Streamlit + Plotly portal (`dashboard/`) sits on top of these exact result
files — no separate computation, just different views of the same
`trades.csv` / `positions_timeline.csv` / `mtm_timeline.csv` / `daily_summary.csv`:

- **Home** — the month overview: cumulative PnL, a click-to-drill daily PnL
  chart, rolls-per-day, and auto-generated findings, for whichever strategy is
  selected in the sidebar.
- **Day Drilldown** — pick any date: intraday MTM with roll markers, the
  futures-vs-selected-strike overlay (§4.8), and the held CE/PE leg price
  stitched across every roll that day.
- **Roll & Turnover Analytics** — holding-duration histogram, a date×hour
  trade-activity heatmap, turnover-vs-PnL scatter.
- **PnL Attribution** — NIFTY vs. BANKNIFTY, CE vs. PE, drawdown, best/worst
  days.

**Deployment note:** the live dashboard runs on Streamlit Community Cloud from
this repository without the raw ~GB-scale dataset present at all. The four
per-strategy result files are shipped as compressed Parquet
(`scripts/export_parquet.py`), and the two charts that would otherwise need
live access to raw tick files (the futures overlay and the held-leg price
chart) instead read from small precomputed Parquet artifacts built once
locally (`scripts/export_market_data.py`) — the dashboard prefers these
precomputed files and only falls back to reading raw ticks live when running
somewhere the full dataset actually exists.

If you'd rather read numbers than click through pages, this report already
covers the same ground in §4.

---

## 9. How to run

```bash
# 1. Dependencies (pandas, numpy, pyarrow, plus streamlit/plotly for the dashboard)
pip install -r dashboard/requirements.txt

# 2. One-time prep of metadata/expiry/universe CSVs (already committed under results/)
python data_cleaning/step_1_1_dataset_inventory.py
python data_cleaning/step_1_2_parse_filenames.py
python data_cleaning/nearest_expiry_selector.py
python engine/filtered_option_universe.py

# 3. Run the backtest — all strategies, or one
python run_strategy.py --all
python run_strategy.py --strategy closest_strike_straddle
python run_strategy.py --list

# 4. (Optional, needs the raw dataset) regenerate the deployment/report artifacts
python scripts/export_parquet.py
python scripts/export_market_data.py
python scripts/generate_report_assets.py

# 5. Launch the interactive portal
cd dashboard && streamlit run Home.py
```

Steps 1–3 need only the raw dataset placed at either
`Backtesting-Engine/Data/allData/` or the repository root's `Data/allData/`
(the code checks both). Step 4 is only needed to regenerate the Parquet/report
artifacts already committed to this repo.

---

## 10. Output files & repository layout

Per strategy, under `results/strategies/<strategy_key>/` (the default
strategy's outputs are also mirrored to `results/` root):

| File | Schema | Description |
|---|---|---|
| `trades.csv` | D3 | Every fill: date, timestamp, underlier, expiry, strike, option_type, instrument_name, direction, price, quantity, reason. |
| `positions_timeline.csv` | D4 | State-change rows: strike, CE/PE instruments, entry prices & timestamps, trigger. |
| `mtm_timeline.csv` | D5 | Per-second realized/unrealized/total PnL for NIFTY, BANKNIFTY, and combined. |
| `daily_summary.csv` | D6 | One row per (date, underlier): trade/roll counts, gross PnL, first-entry/last-roll times, unique strikes held, max favorable/adverse excursion. |
| `held_leg_prices.parquet` | — | Precomputed CE/PE price actually held each second, stitched across rolls (deployment/report support file). |

Plus, strategy-independent: `results/futures_intraday.parquet` (all 21 days,
both underliers) and the Phase 1–3 intermediate CSVs (`option_metadata.csv`,
`nearest_expiry.csv`, `filtered_option_universe.csv`, `strike_map.csv`, …).

Full schema definitions: **[`docs/DELIVERABLES.md`](docs/DELIVERABLES.md)**.
Edge-case handling notes: **[`docs/EDGE_CASES.md`](docs/EDGE_CASES.md)**.
Dashboard internals: **[`dashboard/README.md`](dashboard/README.md)**.

---

*Governing documents: [`docs/SPEC.md`](docs/SPEC.md) (the 11 rules),
[`docs/ASSUMPTIONS.md`](docs/ASSUMPTIONS.md) (the 20 resolved edge cases),
[`docs/DELIVERABLES.md`](docs/DELIVERABLES.md) (output schemas),
[`docs/backtest-workflow-plan.md`](docs/backtest-workflow-plan.md) (the original execution plan).*
