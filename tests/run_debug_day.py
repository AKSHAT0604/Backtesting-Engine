"""
run_debug_day.py — Phase 6, Step 6.1/6.2: Isolated single-day debug run.

Runs the backtest exclusively on NIFTY for 2022-11-01 with verbose logging.
Produces debug_reconciliation.csv with per-second state for manual inspection.
"""

from __future__ import annotations

import logging
import math
import re
import sys
from pathlib import Path

import pandas as pd

# Configure verbose logging BEFORE imports that use logger.
logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)-5s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("debug_day")

# Suppress noisy pandas warnings.
import warnings
warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)

# Engine modules live in ../engine — put it on the path before importing them.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from futures_loader import load_all_futures
from filtered_option_universe import build_filtered_option_universe
from second_grid_builder import build_all_second_grids
from strike_map import build_strike_map, get_eligible_strikes
from instrument_selector import select_strike
from portfolio_state import PortfolioState
from execution_engine import ExecutionEngine
from day_lifecycle import get_day_lifecycle_rules


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
TEST_DATE = "2022-11-01"
TEST_UNDERLIER = "NIFTY"
from data_paths import resolve_data_root, results_dir
DATA_ROOT = resolve_data_root()
RESULTS_DIR = results_dir()
OUTPUT_CSV = RESULTS_DIR / "debug_reconciliation.csv"


def main():
    print("=" * 70)
    print(f"DEBUG DAY: {TEST_DATE} / {TEST_UNDERLIER}")
    print("=" * 70)

    # ---- Load data --------------------------------------------------------
    logger.info("Loading futures for %s...", TEST_DATE)
    futures_store = load_all_futures(DATA_ROOT, [TEST_DATE])

    logger.info("Loading filtered option universe...")
    meta = pd.read_csv(RESULTS_DIR / "option_metadata.csv", dtype=str)
    expiry = pd.read_csv(RESULTS_DIR / "nearest_expiry.csv", dtype=str)
    universe = build_filtered_option_universe(meta, expiry)

    # Log nearest expiry.
    expiry_row = expiry[
        (expiry["trade_date"] == TEST_DATE) & (expiry["underlier"] == TEST_UNDERLIER)
    ]
    selected_expiry = expiry_row.iloc[0]["selected_expiry"] if not expiry_row.empty else "UNKNOWN"
    logger.info("NEAREST EXPIRY for %s %s: %s", TEST_DATE, TEST_UNDERLIER, selected_expiry)

    logger.info("Building 1-second grid...")
    grids = build_all_second_grids([TEST_DATE], futures_store, universe, DATA_ROOT)
    grid = grids[(TEST_DATE, TEST_UNDERLIER)]

    logger.info("Building strike map...")
    smap = build_strike_map(universe)
    eligible_strikes, strike_lookup = get_eligible_strikes(smap, TEST_DATE, TEST_UNDERLIER)
    logger.info("Eligible strikes: %d  (range: %s to %s)",
                len(eligible_strikes), min(eligible_strikes), max(eligible_strikes))

    # ---- Run debug simulation ---------------------------------------------
    portfolio = PortfolioState()
    engine = ExecutionEngine(portfolio, TEST_DATE, TEST_UNDERLIER)
    lifecycle = get_day_lifecycle_rules()

    timeline_rows = []
    prev_strike = None
    trade_count = 0
    roll_count = 0
    squareoff_count = 0

    for ts in grid.index:
        row = grid.loc[ts]
        futures_price = row.get("futures_price")
        is_squareoff = lifecycle.is_forced_squareoff(ts)

        # ---- Determine target ---------------------------------------------
        if is_squareoff:
            target_holdings = {}
            target_strike = None
        else:
            target_strike = select_strike(futures_price, eligible_strikes)
            if target_strike is not None:
                ce_instr, pe_instr = strike_lookup[target_strike]
                ce_price = row.get(ce_instr)
                pe_price = row.get(pe_instr)
                ce_ok = ce_price is not None and not (isinstance(ce_price, float) and math.isnan(ce_price))
                pe_ok = pe_price is not None and not (isinstance(pe_price, float) and math.isnan(pe_price))
                if ce_ok and pe_ok:
                    target_holdings = {ce_instr: 1, pe_instr: 1}
                else:
                    target_holdings = {k: v for k, v in portfolio.current_positions.items() if v > 0}
                    target_strike = prev_strike
            else:
                target_holdings = {k: v for k, v in portfolio.current_positions.items() if v > 0}

        # ---- Log strike changes -------------------------------------------
        if target_strike != prev_strike and not is_squareoff:
            logger.info(
                "STRIKE CHANGE @ %s: futures=%.2f, old_strike=%s, new_strike=%s",
                ts.strftime("%H:%M:%S"),
                futures_price if futures_price else 0,
                prev_strike, target_strike,
            )

        # ---- Build prices dict --------------------------------------------
        all_instruments = portfolio.held_instruments() | {k for k, v in target_holdings.items() if v > 0}
        current_prices = {}
        for instr in all_instruments:
            p = row.get(instr)
            if p is not None and not (isinstance(p, float) and math.isnan(p)):
                current_prices[instr] = float(p)

        # ---- Execute ------------------------------------------------------
        new_trades = engine.process_target_changes(
            timestamp=ts,
            target_holdings=target_holdings,
            current_market_prices=current_prices,
            force_squareoff=is_squareoff,
        )

        trade_action = "None"
        trade_exec_price = ""

        if new_trades:
            trade_count += len(new_trades)
            reason = new_trades[0].reason
            if reason == "SQUAREOFF":
                squareoff_count += 1
            elif reason == "ROLL":
                roll_count += 1

            for t in new_trades:
                logger.info(
                    "  ORDER @ %s: %s %s %s @ %.2f (reason=%s)",
                    ts.strftime("%H:%M:%S"),
                    t.direction, t.quantity, t.instrument_name,
                    t.price, t.reason,
                )

            directions = set(t.direction for t in new_trades)
            if "SELL" in directions and "BUY" in directions:
                trade_action = "ROLL"
            elif "BUY" in directions:
                trade_action = "BUY"
            elif "SELL" in directions:
                trade_action = "SELL"

            prices_str = "; ".join(f"{t.direction}:{t.instrument_name}@{t.price:.2f}" for t in new_trades)
            trade_exec_price = prices_str

        # ---- Update MTM ---------------------------------------------------
        portfolio.update_mtm(current_prices)

        # ---- Determine held instruments -----------------------------------
        held = portfolio.held_instruments()
        held_ce = ""
        held_pe = ""
        for s, (ce, pe) in strike_lookup.items():
            if ce in held:
                held_ce = ce
            if pe in held:
                held_pe = pe

        # ---- Log timeline row ---------------------------------------------
        timeline_rows.append({
            "Timestamp": ts,
            "Futures_Price": futures_price,
            "Target_Strike": target_strike,
            "Held_CE": held_ce,
            "Held_PE": held_pe,
            "Trade_Action_Taken": trade_action,
            "Trade_Execution_Price": trade_exec_price,
            "Total_MTM": portfolio.total_mtm,
        })

        prev_strike = target_strike if not is_squareoff else None

    # ---- Save reconciliation CSV ------------------------------------------
    timeline_df = pd.DataFrame(timeline_rows)
    timeline_df.to_csv(OUTPUT_CSV, index=False)
    logger.info("Saved debug_reconciliation.csv: %d rows -> %s", len(timeline_df), OUTPUT_CSV)

    # ---- Summary ----------------------------------------------------------
    print("\n" + "=" * 70)
    print("DEBUG DAY SUMMARY")
    print("=" * 70)
    print(f"Date / Underlier  : {TEST_DATE} / {TEST_UNDERLIER}")
    print(f"Nearest Expiry    : {selected_expiry}")
    print(f"Total fills       : {trade_count}")
    print(f"Roll events       : {roll_count}")
    print(f"Squareoff events  : {squareoff_count}")
    print(f"Final Realized PnL: {portfolio.realized_pnl:.2f}")
    print(f"Final Total MTM   : {portfolio.total_mtm:.2f}")
    print(f"Portfolio is flat  : {portfolio.is_flat()}")

    # ---- Verify squareoff happened exactly once ---------------------------
    if squareoff_count == 1:
        print("\nPASS: End-of-day squareoff executed exactly once.")
    else:
        print(f"\nFAIL: Expected 1 squareoff, got {squareoff_count}.")

    print(f"\nDebug CSV: {OUTPUT_CSV}")
    print("Done.")


if __name__ == "__main__":
    main()
