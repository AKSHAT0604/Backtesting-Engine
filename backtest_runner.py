"""
backtest_runner.py — Phase 5, Steps 5.3/5.4: Main backtest loop.

Wires together: PortfolioState, ExecutionEngine, Strategy, Lifecycle rules,
and the 1-second grid to produce trades, MTM timeline, and positions timeline.

Data loading strategy: Each day's second-grid DataFrame (~28 MB per underlier)
is loaded fully into memory before the 22,500-second loop. This is the correct
approach — row-by-row file I/O would be catastrophically slow.

Governed by:
    SPEC.md Rules 7-11
    ASSUMPTIONS.md A1, A3, A5, A8, A9, A13, A14
    DELIVERABLES.md D3, D4, D5
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

import pandas as pd

from portfolio_state import PortfolioState
from execution_engine import ExecutionEngine, TradeRecord
from instrument_selector import select_strike
from day_lifecycle import get_day_lifecycle_rules, SESSION_START_TIME, SESSION_END_TIME

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Single-day backtest
# ---------------------------------------------------------------------------

def run_single_day(
    trade_date: str,
    underlier: str,
    second_grid: pd.DataFrame,
    strike_lookup: dict[int | float, tuple[str, str]],
) -> tuple[list[TradeRecord], list[dict], list[dict]]:
    """Run the backtest for one (trade_date, underlier).

    Parameters
    ----------
    trade_date : str
        Trading day in YYYY-MM-DD format.
    underlier : str
        "NIFTY" or "BANKNIFTY".
    second_grid : pd.DataFrame
        Wide grid indexed by 22,500-second DatetimeIndex.
        Column "futures_price" + one column per option instrument.
    strike_lookup : dict
        Maps eligible strike -> (ce_instrument_name, pe_instrument_name).

    Returns
    -------
    trades : list[TradeRecord]
        All fills for this day/underlier.
    mtm_log : list[dict]
        Per-second MTM snapshots (22,500 entries).
    positions_log : list[dict]
        State-change entries for the positions timeline.
    """
    portfolio = PortfolioState()
    engine = ExecutionEngine(portfolio, trade_date, underlier)
    lifecycle = get_day_lifecycle_rules()
    available_strikes = sorted(strike_lookup.keys())

    trades: list[TradeRecord] = []
    mtm_log: list[dict] = []
    positions_log: list[dict] = []

    # Track last recorded position state for change detection.
    last_position_state: tuple | None = None  # (strike, ce, pe) or None

    for ts in second_grid.index:
        # ---- 1. Read market state at this second --------------------------
        row = second_grid.loc[ts]
        futures_price = row.get("futures_price")

        # ---- 2. Determine target holdings ---------------------------------
        is_squareoff = lifecycle.is_forced_squareoff(ts)

        if is_squareoff:
            # Override: target is flat regardless of strategy.
            target_holdings: dict[str, int] = {}
            selected_strike = None
        else:
            # Use strategy logic: closest strike.
            selected_strike = select_strike(futures_price, available_strikes)

            if selected_strike is not None:
                ce_instr, pe_instr = strike_lookup[selected_strike]

                # Check both legs have valid prices (A5).
                ce_price = row.get(ce_instr)
                pe_price = row.get(pe_instr)
                ce_ok = ce_price is not None and not (isinstance(ce_price, float) and math.isnan(ce_price))
                pe_ok = pe_price is not None and not (isinstance(pe_price, float) and math.isnan(pe_price))

                if ce_ok and pe_ok:
                    target_holdings = {ce_instr: 1, pe_instr: 1}
                else:
                    # Can't enter/roll — keep current or stay flat.
                    target_holdings = {k: v for k, v in portfolio.current_positions.items() if v > 0}
                    selected_strike = None
            else:
                # No valid strike — keep current or stay flat.
                target_holdings = {k: v for k, v in portfolio.current_positions.items() if v > 0}

        # ---- 3. Build current market prices dict for held + target --------
        all_instruments = portfolio.held_instruments() | {k for k, v in target_holdings.items() if v > 0}
        current_prices = {}
        for instr in all_instruments:
            p = row.get(instr)
            if p is not None and not (isinstance(p, float) and math.isnan(p)):
                current_prices[instr] = float(p)

        # ---- 4. Execute changes -------------------------------------------
        new_trades = engine.process_target_changes(
            timestamp=ts,
            target_holdings=target_holdings,
            current_market_prices=current_prices,
            force_squareoff=is_squareoff,
        )
        trades.extend(new_trades)

        # ---- 5. Update MTM -----------------------------------------------
        portfolio.update_mtm(current_prices)

        # ---- 6. Log MTM snapshot ------------------------------------------
        mtm_log.append({
            "timestamp": ts,
            "realized_pnl": portfolio.realized_pnl,
            "unrealized_pnl": portfolio.unrealized_pnl,
            "total_pnl": portfolio.total_mtm,
        })

        # ---- 7. Log position state changes --------------------------------
        held = portfolio.held_instruments()
        if held:
            held_sorted = sorted(held)
            # Determine current strike from held instruments.
            current_strike = None
            current_ce = None
            current_pe = None
            for s, (ce, pe) in strike_lookup.items():
                if ce in held or pe in held:
                    current_strike = s
                    current_ce = ce
                    current_pe = pe
                    break
            pos_state = (current_strike, current_ce, current_pe)
        else:
            pos_state = None

        if pos_state != last_position_state:
            # Determine trigger.
            if last_position_state is None and pos_state is not None:
                if lifecycle.is_session_start(ts):
                    trigger = "ENTRY"
                else:
                    trigger = "ENTRY"
            elif last_position_state is not None and pos_state is None:
                if is_squareoff:
                    trigger = "SQUAREOFF"
                else:
                    trigger = "FLAT_NO_PRICE"
            elif last_position_state is not None and pos_state is not None:
                trigger = "ROLL"
            else:
                trigger = "SESSION_START"

            positions_log.append({
                "trade_date": trade_date,
                "timestamp": ts,
                "underlier": underlier,
                "state": "HOLDING" if pos_state else "FLAT",
                "strike": pos_state[0] if pos_state else None,
                "ce_instrument": pos_state[1] if pos_state else None,
                "ce_entry_price": portfolio.entry_prices.get(pos_state[1]) if pos_state else None,
                "pe_instrument": pos_state[2] if pos_state else None,
                "pe_entry_price": portfolio.entry_prices.get(pos_state[2]) if pos_state else None,
                "trigger": trigger,
            })
            last_position_state = pos_state

    logger.info(
        "[%s] %s: day complete — %d trades, final realized=%.2f, total_mtm=%.2f",
        trade_date, underlier, len(trades),
        portfolio.realized_pnl, portfolio.total_mtm,
    )

    return trades, mtm_log, positions_log


# ---------------------------------------------------------------------------
# Full backtest across all days
# ---------------------------------------------------------------------------

def run_full_backtest(
    trade_dates: list[str],
    grids: dict[tuple[str, str], pd.DataFrame],
    strike_map: dict[tuple[str, str], pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run the backtest across all days and both underliers.

    Parameters
    ----------
    trade_dates : list[str]
        Ordered trading dates.
    grids : dict[(trade_date, underlier), pd.DataFrame]
        Second-grid DataFrames from build_all_second_grids.
    strike_map : dict[(trade_date, underlier), pd.DataFrame]
        From build_strike_map (Step 3.1).

    Returns
    -------
    trades_df : pd.DataFrame
        All trade records across the full backtest.
    mtm_df : pd.DataFrame
        Per-second MTM timeline with per-underlier and combined columns.
    positions_df : pd.DataFrame
        Position state-change records.
    """
    from strike_map import get_eligible_strikes

    all_trades: list[TradeRecord] = []
    nifty_mtm: list[dict] = []
    banknifty_mtm: list[dict] = []
    all_positions: list[dict] = []

    underliers = ["NIFTY", "BANKNIFTY"]

    for trade_date in trade_dates:
        for underlier in underliers:
            key = (trade_date, underlier)

            grid = grids.get(key)
            if grid is None or grid.empty:
                logger.warning("[%s] %s: no grid available, skipping.", trade_date, underlier)
                continue

            _, strike_lookup = get_eligible_strikes(strike_map, trade_date, underlier)
            if not strike_lookup:
                logger.warning("[%s] %s: no eligible strikes, skipping.", trade_date, underlier)
                continue

            day_trades, day_mtm, day_positions = run_single_day(
                trade_date, underlier, grid, strike_lookup,
            )

            all_trades.extend(day_trades)
            all_positions.extend(day_positions)

            if underlier == "NIFTY":
                nifty_mtm.extend(day_mtm)
            else:
                banknifty_mtm.extend(day_mtm)

    # ---- Build trades DataFrame -------------------------------------------
    trades_df = pd.DataFrame([t._asdict() for t in all_trades])

    # ---- Build MTM timeline (per-underlier + combined) --------------------
    nifty_df = pd.DataFrame(nifty_mtm).rename(columns={
        "realized_pnl": "nifty_realized_pnl",
        "unrealized_pnl": "nifty_unrealized_pnl",
        "total_pnl": "nifty_total_pnl",
    })
    banknifty_df = pd.DataFrame(banknifty_mtm).rename(columns={
        "realized_pnl": "banknifty_realized_pnl",
        "unrealized_pnl": "banknifty_unrealized_pnl",
        "total_pnl": "banknifty_total_pnl",
    })

    # Merge on timestamp.
    mtm_df = nifty_df.merge(banknifty_df, on="timestamp", how="outer").sort_values("timestamp")
    mtm_df["combined_total_pnl"] = (
        mtm_df["nifty_total_pnl"].fillna(0) + mtm_df["banknifty_total_pnl"].fillna(0)
    )

    # Add trade_date column.
    mtm_df["trade_date"] = mtm_df["timestamp"].dt.strftime("%Y-%m-%d")

    # ---- Build positions DataFrame ----------------------------------------
    positions_df = pd.DataFrame(all_positions)

    return trades_df, mtm_df, positions_df


# ---------------------------------------------------------------------------
# Standalone runner — runs full backtest and saves outputs
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import re
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(message)s",
        stream=sys.stdout,
    )

    from futures_loader import load_all_futures
    from filtered_option_universe import build_filtered_option_universe
    from second_grid_builder import build_all_second_grids
    from strike_map import build_strike_map

    SCRIPT_DIR = Path(__file__).resolve().parent
    DATA_ROOT = SCRIPT_DIR / "Data" / "allData"
    RESULTS_DIR = SCRIPT_DIR / "results"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # ---- Discover trade dates ---------------------------------------------
    _FOLDER_RE = re.compile(r"^NSE_(\d{8})$")
    trade_dates = []
    for d in sorted(DATA_ROOT.iterdir()):
        m = _FOLDER_RE.match(d.name)
        if m and d.is_dir():
            raw = m.group(1)
            trade_dates.append(f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}")

    print("=" * 70)
    print("PHASE 5 — FULL BACKTEST")
    print("=" * 70)
    print(f"Trading days: {len(trade_dates)}")
    print(f"Underliers : NIFTY, BANKNIFTY\n")

    # ---- Load all data ----------------------------------------------------
    print("1. Loading futures...")
    futures_store = load_all_futures(DATA_ROOT, trade_dates)

    print("2. Loading filtered option universe...")
    meta = pd.read_csv(RESULTS_DIR / "option_metadata.csv", dtype=str)
    expiry = pd.read_csv(RESULTS_DIR / "nearest_expiry.csv", dtype=str)
    universe = build_filtered_option_universe(meta, expiry)

    print("3. Building 1-second grids (this takes ~2 min)...")
    grids = build_all_second_grids(trade_dates, futures_store, universe, DATA_ROOT)

    print("4. Building strike map...")
    smap = build_strike_map(universe)

    # ---- Run full backtest ------------------------------------------------
    print("\n5. Running backtest loop...\n")
    trades_df, mtm_df, positions_df = run_full_backtest(trade_dates, grids, smap)

    # ---- Save outputs -----------------------------------------------------
    trades_path = RESULTS_DIR / "trades.csv"
    mtm_path = RESULTS_DIR / "mtm_timeline.csv"
    positions_path = RESULTS_DIR / "positions_timeline.csv"

    trades_df.to_csv(trades_path, index=False)
    mtm_df.to_csv(mtm_path, index=False)
    positions_df.to_csv(positions_path, index=False)

    print(f"\nSaved trades.csv           : {len(trades_df)} rows -> {trades_path}")
    print(f"Saved mtm_timeline.csv     : {len(mtm_df)} rows -> {mtm_path}")
    print(f"Saved positions_timeline.csv: {len(positions_df)} rows -> {positions_path}")

    # ---- Summary ----------------------------------------------------------
    print("\n" + "=" * 70)
    print("BACKTEST SUMMARY")
    print("=" * 70)

    if not trades_df.empty:
        print(f"\nTotal trades: {len(trades_df)}")
        print(f"  ENTRY     : {len(trades_df[trades_df['reason'] == 'ENTRY'])}")
        print(f"  ROLL      : {len(trades_df[trades_df['reason'] == 'ROLL'])}")
        print(f"  SQUAREOFF : {len(trades_df[trades_df['reason'] == 'SQUAREOFF'])}")

        for ul in ["NIFTY", "BANKNIFTY"]:
            ul_trades = trades_df[trades_df["underlier"] == ul]
            print(f"\n  {ul}:")
            print(f"    Total fills   : {len(ul_trades)}")
            print(f"    Roll events   : {len(ul_trades[ul_trades['reason'] == 'ROLL']) // 4}")

    # Final PnL from MTM.
    if not mtm_df.empty:
        last_row = mtm_df.iloc[-1]
        print(f"\nFinal PnL:")
        print(f"  NIFTY      : {last_row.get('nifty_total_pnl', 0):.2f}")
        print(f"  BANKNIFTY  : {last_row.get('banknifty_total_pnl', 0):.2f}")
        print(f"  Combined   : {last_row.get('combined_total_pnl', 0):.2f}")

    print("\nDone.")
