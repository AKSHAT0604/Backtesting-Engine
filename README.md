# NSE Options Intraday Backtesting Engine

A backtest of an intraday options strategy over one month (November 2022) of NSE
tick data, for **NIFTY** and **BANKNIFTY**. The engine is strategy-agnostic: it
consumes *target positions* from a pluggable strategy and books the trades,
mark-to-market PnL, and position history that result.

---

## 1. Assignment objective

For each trading day, at every second, hold a long straddle (1 CE + 1 PE) at the
strike closest to the futures price; roll both legs whenever the closest strike
changes; square everything off at the end of the day. Run this for NIFTY and
BANKNIFTY across the whole month and produce mark-to-market PnL over time and the
positions held at any point in time. The goal is a correct, auditable backtest —
not a profitable strategy.

## 2. Dataset structure

```
Data/allData/
  NSE_YYYYMMDD/                     # one folder per trading day (21 days)
    Futures (Continuous)/
      NIFTY-I.csv  BANKNIFTY-I.csv  # only the -I continuous contract is used
      ... (-II, -III, FINNIFTY ignored)
    Options/
      {UNDERLIER}{YYMMDD}{STRIKE}{CE|PE}.csv   # e.g. NIFTY22110318150CE.csv
```

Every CSV is headerless with five columns: `Date, Time, Price, Volume, Open Interest`.
The option identity (underlier, expiry, strike, type) is encoded entirely in the
filename. The dataset is **not** included in this repo; place it at either
`Backtesting-Engine/Data/allData/` or the repo root `Data/allData/` — the code
finds it in either location.

## 3. Strategy rules (the 11 rules)

One month of data · date-by-date, no cross-day carry · NIFTY + BANKNIFTY only
(never FINNIFTY/MIDCPNIFTY) · futures from `-I.csv` only · nearest-expiry options
only · max 1 unit per instrument · evaluate every second · long closest-strike
CE+PE · roll both legs on strike change · forced end-of-day square-off · output
MTM PnL over time and the position record.

The authoritative rule text is **[`../SPEC.md`](../SPEC.md)** (at the repo root).

## 4. Assumptions

All 20 resolved assumptions are in **[`../ASSUMPTIONS.md`](../ASSUMPTIONS.md)**
(repo root). The load-bearing ones:

- 1-second grid `09:15:00`–`15:29:59` (22,500 seconds); last tick per second wins;
  forward-fill; no price before an instrument's first tick (A1–A4).
- A strike is tradable only if **both** CE and PE exist *and* both are priced;
  otherwise the strategy stays flat / exits (A5, A7).
- Closest-strike ties break to the **lower** strike (A6).
- Fills at the marked (last-traded, forward-filled) price; **no** costs, slippage,
  or latency (A8, A10, A11).
- NIFTY and BANKNIFTY are managed independently; combined PnL is their sum (A12).

## 5. Design & architecture

The pipeline is a clean sequence of small, independently runnable modules:

| Stage | Module | Output |
|---|---|---|
| Inventory / parse | `step_1_1_dataset_inventory.py`, `option_filename_parser.py` | `results/option_metadata.csv` |
| Nearest expiry | `nearest_expiry_selector.py` | `results/nearest_expiry.csv` |
| Filtered universe | `filtered_option_universe.py` | `results/filtered_option_universe.csv` |
| Futures load | `futures_loader.py` | standardized futures frames |
| 1-second grid | `second_grid_builder.py` | per-day wide price grids |
| Strike map | `strike_map.py` | eligible (both-legs) strikes |
| Strike selection | `instrument_selector.py` | `select_strike`, target pair |
| **Strategy** | `strategies/` package | target positions per second |
| **Engine** | `backtest_runner.py` | trades / MTM / positions |
| Portfolio / execution | `portfolio_state.py`, `execution_engine.py` | ledger + fills |
| Reporting | `reporting.py` | enriched trades + D6 daily summary |
| Orchestration | `run_strategy.py` | writes all outputs per strategy |

**The key design choice — strategy/engine decoupling.** A strategy is a *pure
function* of `(timestamp, MarketState) → {instrument: 1}` desired holdings. It
never books trades or reads the portfolio. The `ExecutionEngine` computes the diff
from current holdings to that target and emits SELL-before-BUY fills. This is what
makes strategies swappable without touching the engine, execution, or accounting.

### Pluggable strategies

Strategies live in **`strategies/`** and self-register via a decorator:

```python
# strategies/my_strategy.py
from strategies.base import Strategy, MarketState, register_strategy

@register_strategy(key="my_strategy", name="My Strategy", description="…")
class MyStrategy(Strategy):
    def get_target_positions(self, timestamp, market_state) -> dict[str, int]:
        strike = ...                       # your selection logic
        return market_state.pair_if_tradable(strike)   # {ce:1, pe:1} or {}
```

**To add a strategy you only add one file in `strategies/`.** Auto-discovery
registers it, so the engine can run it (`python run_strategy.py --strategy my_strategy`)
and the dashboard lists it in the strategy dropdown — no other edits. A fresh
strategy instance is created per (day, underlier), so strategies may hold internal
per-day state (they just must not read the portfolio).

Bundled strategies:

| Key | Name | Behavior |
|---|---|---|
| `closest_strike_straddle` | Closest-Strike Long Straddle | **The assignment strategy** — ATM straddle, rolled on every closest-strike change. |
| `farthest_strike_straddle` | Farthest-Strike (dummy) | Deep-OTM straddle at the farthest eligible strike; very low turnover. |
| `atm_open_hold_straddle` | ATM-at-Open Buy & Hold (dummy) | Lock the ATM straddle at open, hold until EOD square-off (stateful; zero rolls). |

## 6. How to run

```bash
# 1. Dependencies (pandas, numpy, plus streamlit/plotly for the dashboard)
pip install -r dashboard/requirements.txt

# 2. One-time prep of metadata/expiry/universe CSVs (already in results/)
python step_1_1_dataset_inventory.py
python step_1_2_parse_filenames.py
python nearest_expiry_selector.py
python filtered_option_universe.py

# 3. Run the backtest — all strategies, or one
python run_strategy.py --all
python run_strategy.py --strategy closest_strike_straddle
python run_strategy.py --list

# 4. Launch the interactive portal
cd dashboard && streamlit run Home.py
```

## 7. Output files

Per strategy, under `results/strategies/<strategy_key>/` (the default strategy is
also mirrored to `results/` root for the notebook):

| File | Schema | Description |
|---|---|---|
| `trades.csv` | D3 | Every fill: date, timestamp, underlier, expiry, strike, option_type, instrument_name, direction, price, quantity, reason. |
| `positions_timeline.csv` | D4 | State-change rows: strike, CE/PE instruments, entry prices & timestamps, trigger. |
| `mtm_timeline.csv` | D5 | Per-second realized/unrealized/total PnL for NIFTY, BANKNIFTY, and combined. |
| `daily_summary.csv` | D6 | One row per (date, underlier): trade/roll counts, gross PnL, first-entry/last-roll times, unique strikes held, max favorable/adverse excursion. |

Full schema definitions are in [`DELIVERABLES.md`](DELIVERABLES.md).

## 8. Interactive analysis portal

`dashboard/` is a Streamlit + Plotly portal (the presentation layer). Pick a
strategy in the sidebar and explore: month overview with a click-to-drill daily
PnL chart, per-day intraday MTM with roll markers and a futures-vs-strike overlay,
roll/turnover analytics (holding-duration histogram, date×hour heatmap), and PnL
attribution (NIFTY vs BANKNIFTY, CE vs PE, drawdown). If a newly added strategy
has no results yet, the portal offers a button to run the engine for it. See
[`dashboard/README.md`](dashboard/README.md).

## 9. Key findings (default closest-strike strategy)

- The closest-strike straddle rolls **heavily** — hundreds of rolls per day per
  underlier — because the ATM strike flips as futures oscillate second-to-second.
- **BANKNIFTY** carries higher turnover than NIFTY (wider point moves, 100-pt
  strike spacing), and drives most of the month's PnL swing.
- With zero costs the month is modestly **negative** overall: the strategy
  repeatedly pays the bid/mark round-trip on whipsaw rolls (buy-high/sell-low churn).
- PnL is **concentrated** in a few high-volatility days rather than evenly spread.
- The two dummy strategies confirm the framework: the deep-OTM and ATM-hold
  variants run through the identical engine with near-zero turnover and very
  different PnL, changing *only* their target-selection rule.

(The dashboard's Home page recomputes these numbers live for whichever strategy
is selected.)

## 10. Limitations

- **Idealized execution:** no transaction costs, slippage, spread, or latency
  (base scope, A10/A11). Real closest-strike churn would bleed far more after costs.
- **Marked-price fills:** entries/exits use the last-traded/forward-filled price,
  not a bid/ask — optimistic for a high-turnover strategy.
- **No liquidity model:** a leg is "available" once it has ticked; depth is ignored.
- **Single month, two underliers**, by design.

---

*Governing documents: [`../SPEC.md`](../SPEC.md) (rules), [`../ASSUMPTIONS.md`](../ASSUMPTIONS.md)
(assumptions), [`DELIVERABLES.md`](DELIVERABLES.md) (output schemas),
[`EDGE_CASES.md`](EDGE_CASES.md) (edge-case handling).*
