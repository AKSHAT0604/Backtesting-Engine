# Backtesting Project Workflow Plan

This document is a rigorous execution plan for building, validating, and packaging the NSE options backtesting assignment. The goal is to finish the base project requirements first in a disciplined order, while keeping the codebase flexible enough to add creative improvements later without breaking the core system.[cite:1]

## Project Objective

The assignment is to build a backtest over the November 2022 intraday derivatives dataset, using daily folders under `Data/allData/`, with futures data from the `-I.csv` files and option data from per-instrument CSVs whose filenames encode underlier, expiry, strike, and option type.[cite:1]

The strategy must run for both NIFTY and BANKNIFTY, trade only the nearest-expiry option contracts for the current date, select the strike closest to the corresponding futures price at each second, buy both the CE and PE, roll both legs when the closest strike changes, and close all positions at day end.[cite:1]

## Delivery Mindset

The work should be done in two layers: first complete the **base assignment engine** exactly as asked, then add enhancements only after the engine is correct, auditable, and reproducible.[cite:1]

This prevents a common failure mode in such projects: spending time on charts, dashboards, or optimizations before the core trading logic, PnL accounting, and daily processing are trustworthy.[cite:1]

## Phase 0: Scope Lock

### Step 0.1: Freeze what the assignment actually requires

Write down the non-negotiable rules in one page before coding:

- Use one month of data in `Data/allData/`.[cite:1]
- Work date by date using the dated NSE folders.[cite:1]
- Use only NIFTY and BANKNIFTY.[cite:1]
- Use only `UNDERLIER-I.csv` in futures.[cite:1]
- Use only nearest-expiry options for that date.[cite:1]
- Max position per instrument is 1.[cite:1]
- Evaluate serially through the day at 1-second resolution.[cite:1]
- Hold long CE + long PE at the strike closest to futures price.[cite:1]
- Roll both legs when the closest strike changes.[cite:1]
- Close all positions at day end.[cite:1]
- Produce mark-to-market PnL and position details over time.[cite:1]

### Step 0.2: Lock assumptions that are not fully specified

Create an `ASSUMPTIONS.md` section inside the README or report before implementation. Recommended assumptions:

- Intraday timestamps are aligned to a 1-second grid using forward-fill from the latest available tick.[cite:1]
- Entry and exit happen at the latest available option price at that second.[cite:1]
- If both CE and PE prices are not available, skip entry until both become available.
- End-of-day close uses the last available marked price for the open instruments.
- No brokerage, slippage, taxes, or latency in the base version.
- Tie-breaking for closest strike is deterministic, such as choosing the lower strike first.

### Step 0.3: Define the base deliverables now

Before writing code, decide the minimum submission package:

- Source code.
- README or workflow/report document.
- `trades.csv`.
- `positions_timeline.csv`.
- `mtm_timeline.csv`.
- `daily_summary.csv`.
- Cumulative PnL plot.
- Daily PnL plot.
- A short findings section.

This gives a fixed finish line and keeps later “creative additions” separate from required outputs.

## Phase 1: Dataset Understanding

### Step 1.1: Map the directory structure

Confirm the dataset layout and list all trading days. The context file shows 20 trading-day folders in November 2022, each containing a futures folder and an options folder.[cite:1]

Output for this step:

- List of all dates.
- Confirmation that both NIFTY and BANKNIFTY futures files exist for each day.
- Count of option files by underlier and day.

### Step 1.2: Parse option filenames into metadata

Create a parser that extracts:

- Underlier.
- Expiry date.
- Strike.
- Option type.
- Full instrument name.

This metadata is critical because the option identity is encoded entirely in filenames such as `NIFTY22110314550PE.csv` and `BANKNIFTY22112443200CE.csv`.[cite:1]

Output for this step:

- One metadata table per day or one master metadata table.

### Step 1.3: Validate raw file schema

Check that all CSV files follow the expected five-column structure: `Date`, `Time`, `Price`, `Volume`, and `Open Interest`, with chronological rows.[cite:1]

Output for this step:

- A validation note showing that schema is consistent.
- A list of corrupt, empty, or missing files if any exist.

## Phase 2: Market Data Layer

### Step 2.1: Build futures loader

Create a function that reads only `NIFTY-I.csv` and `BANKNIFTY-I.csv` for each trading day, standardizes columns, constructs a proper timestamp, sorts chronologically, and removes duplicates if any.[cite:1]

Output for this step:

- Standardized futures DataFrame for each day and underlier.

### Step 2.2: Build nearest-expiry selector

For each day and underlier, determine the earliest expiry available in option filenames that is still the nearest tradable expiry for that trading date. The assignment example explicitly expects a date such as 20221101 to use NIFTY contracts expiring on 221103 rather than later expiries.[cite:1]

Output for this step:

- Table with columns: trade date, underlier, selected expiry.

### Step 2.3: Build filtered option universe

Once nearest expiry is known, load only those option files for the selected expiry and the relevant underlier. This keeps the project efficient and aligned to the assignment logic.[cite:1]

Output for this step:

- Filtered option universe for each day and underlier.

### Step 2.4: Convert ticks to a 1-second timeline

The assignment requires evaluation at every second, but the dataset is event-level intraday data rather than guaranteed one-row-per-second data.[cite:1]

So create a uniform 1-second time index for the trading session and forward-fill the last seen price for:

- Futures price.
- Each eligible option instrument.

Output for this step:

- A per-day market-state object or tables keyed by 1-second timestamps.

## Phase 3: Instrument Selection Logic

### Step 3.1: Create available strike map

For each underlier and day, build a strike map from the filtered nearest-expiry option universe. Keep CE and PE availability separate so the strategy only trades strikes where both legs exist.

Output for this step:

- Valid tradable strikes per day and underlier.

### Step 3.2: Implement closest-strike selector

At each second, read the current futures price and select the strike with minimum absolute distance to that futures price. Use deterministic tie-breaking.

Output for this step:

- Function: `select_strike(futures_price, available_strikes)`.

### Step 3.3: Convert strike into target instruments

Given the selected strike, map it into:

- One CE instrument.
- One PE instrument.

Both must belong to the same underlier and nearest expiry.

Output for this step:

- Function: `get_target_pair(date, underlier, timestamp)`.

## Phase 4: Strategy Layer

### Step 4.1: Encode target-position logic

The base strategy should be implemented as target holdings, not raw order code. At each second, desired holdings are:

- Long 1 unit of closest-strike CE.
- Long 1 unit of closest-strike PE.
- Zero in all other instruments.

Output for this step:

- Strategy class, for example `ClosestStrikeLongStraddleStrategy`.

### Step 4.2: Add day-start and day-end rules

The strategy must:

- Open the pair once valid prices are available.
- Keep the pair until closest strike changes.
- Force close all open positions at end of day.[cite:1]

Output for this step:

- Explicit day lifecycle rules.

### Step 4.3: Keep strategy decoupled from execution

Do not place trade-booking logic inside the strategy class. The strategy should only declare desired positions; the engine should decide which orders are needed to move from current holdings to target holdings.

This single design choice is what makes later experimentation possible.

## Phase 5: Backtest Engine

### Step 5.1: Build portfolio state model

Track at minimum:

- Current positions.
- Entry price / average price.
- Last marked price.
- Realized PnL.
- Unrealized PnL.
- Total MTM.

Output for this step:

- `PortfolioState` class or equivalent structure.

### Step 5.2: Build order generation from target changes

At every second, compare current holdings with strategy target holdings:

- If target equals current, do nothing.
- If strike changes, sell old CE and PE, then buy new CE and PE.
- Respect max position 1 per instrument.[cite:1]

Output for this step:

- Order generator.
- Fill simulator.

### Step 5.3: Build execution pricing convention

Use a simple, explicit execution rule in the base project:

- Fill at latest available marked option price for that timestamp.

Do not overcomplicate the first version. More realistic execution can be added later as an enhancement.

### Step 5.4: Build mark-to-market accounting

At each second, calculate:

- Unrealized PnL for open positions.
- Realized PnL for closed positions.
- Running total PnL.
- Underlier-wise PnL and combined PnL.

Output for this step:

- MTM time series.

## Phase 6: Validation and Debugging

### Step 6.1: Run one underlier on one date first

Start with one small slice, such as one date of NIFTY only. Do not run the full month immediately.

Check:

- Selected expiry is correct.
- Selected strike changes logically with futures movement.
- Orders are generated only when strike changes.
- End-of-day close happens exactly once.

### Step 6.2: Reconcile one full sample day manually

Pick a sample day and inspect a few timestamp windows by hand:

- Futures price.
- Closest strike.
- Held CE and PE.
- Roll timestamps.
- Trade prices.
- MTM before and after roll.

This is the most important quality-control step in the entire project.

### Step 6.3: Test edge cases

Test explicitly for:

- Missing CE or PE file.
- Missing price at a timestamp.
- Duplicate timestamps.
- Empty file.
- No strike change all day.
- Frequent rapid strike switching.

Output for this step:

- Short edge-case note in README.

## Phase 7: Full Backtest Run

### Step 7.1: Run all dates for NIFTY

Finish a full month run for NIFTY only first. Save outputs separately.

### Step 7.2: Run all dates for BANKNIFTY

Run the full month for BANKNIFTY. Save outputs separately.

### Step 7.3: Run combined portfolio version

Merge both underliers into one total result set.

Output for this step:

- Combined trade log.
- Combined MTM timeline.
- Combined daily summary.

## Phase 8: Reporting Outputs

### Step 8.1: Generate core CSV outputs

Produce at least these files:

- `trades.csv`: executed orders and reasons.
- `positions_timeline.csv`: positions held through time.
- `mtm_timeline.csv`: running PnL by timestamp.
- `daily_summary.csv`: one row per date with summary metrics.

### Step 8.2: Generate charts

Create at minimum:

- Cumulative PnL chart.
- Daily PnL bar chart.
- Optional intraday MTM charts for representative days.
- Optional chart of number of rolls per day.

### Step 8.3: Write concise findings

Include 5 to 10 bullet observations, for example:

- How often the strategy rolled.
- Which underlier had higher turnover.
- Whether PnL was dominated by a few days.
- Whether intraday churn appeared high.
- Any data quality limitations encountered.

## Phase 9: Packaging the Submission

### Step 9.1: Prepare repository structure

Recommended layout:

```text
project/
  src/
    data_loader.py
    instrument_parser.py
    strategy.py
    backtester.py
    reporting.py
  results/
  run_backtest.py
  README.md
  requirements.txt
```

### Step 9.2: Write the README in final form

The README should contain:

- Assignment objective.
- Dataset structure.
- Strategy rules.
- Assumptions.
- Design architecture.
- Run instructions.
- Output file explanations.
- Key findings.
- Limitations.

### Step 9.3: Final QA before submission

Check all of these before sending:

- Code runs end to end from a clean environment.
- File paths are not hardcoded to one machine.
- Outputs are regenerated cleanly.
- Charts match CSV numbers.
- Day-end exits always happen.
- No accidental use of FINNIFTY.
- Only `-I.csv` futures are used.[cite:1]
- Only nearest-expiry options are used.[cite:1]

## Phase 10: Creative Enhancements After Base Completion

These items should only be added after the core assignment is complete and verified.

### Step 10.1: Add configuration-driven strategy parameters

Move hardcoded values into a config file:

- Evaluation frequency.
- Entry start time.
- Exit cutoff time.
- Tie-break rule.
- Slippage model.
- Transaction cost model.

### Step 10.2: Add alternate strategies without changing engine

Examples:

- Rebalance only when strike changes by more than one step.
- Trade only during a chosen intraday window.
- Trade only one side under certain filters.
- Hold until time-based rebalance instead of every strike change.

### Step 10.3: Add richer analytics

Examples:

- Drawdown curve.
- Holding duration distribution.
- Roll frequency histogram.
- PnL by weekday.
- PnL attribution by CE vs PE leg.
- Turnover metrics.

### Step 10.4: Add execution realism

Examples:

- Slippage.
- Fixed or proportional costs.
- Delayed fills.
- No-fill rules when quote is stale.

### Step 10.5: Add presentation layer polish

Examples:

- Interactive notebook.
- HTML dashboard.
- Better charts and annotations.
- Per-day replay plots.
- Strategy comparison report.

These are great additions, but they must sit on top of a correct base engine rather than replacing it.

## Suggested Working Order by Day

This is the safest real-world working sequence:

1. Freeze scope and assumptions.
2. Parse filenames and validate files.
3. Load futures data.
4. Determine nearest expiry by day and underlier.
5. Load only relevant options.
6. Build 1-second aligned market data.
7. Implement closest-strike selection.
8. Implement target-position strategy.
9. Implement backtest engine and MTM.
10. Validate one day manually.
11. Run full month NIFTY.
12. Run full month BANKNIFTY.
13. Merge results.
14. Generate CSV outputs and charts.
15. Write README/report.
16. Add enhancements only if time remains.

## Definition of Done

The base project is complete when all of the following are true:

- The code processes all trading days in the dataset.[cite:1]
- The strategy is implemented exactly for NIFTY and BANKNIFTY.[cite:1]
- Nearest-expiry filtering works correctly.[cite:1]
- Closest-strike CE and PE positions are held and rolled correctly.[cite:1]
- End-of-day square-off works correctly.[cite:1]
- MTM PnL is available over time.[cite:1]
- Trade log and position history are exported.
- Charts are generated.
- The README explains assumptions and workflow clearly.
- The code structure allows new strategies or execution assumptions to be added later.

## Final Recommendation

Treat the assignment as an engineering project, not just a coding exercise. The strongest submission is one where the core logic is correct, the outputs are auditable, the assumptions are explicit, and the structure is flexible enough to support creative extensions after the mandatory requirements are complete.[cite:1]
