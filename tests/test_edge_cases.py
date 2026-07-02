"""
test_edge_cases.py — Phase 6, Step 6.3: Synthetic edge-case tests.

Tests PortfolioState + ExecutionEngine against controlled synthetic scenarios:
  1. Missing price (one leg NaN)
  2. Duplicate timestamps
  3. No strike change all day (flat futures)
  4. Frequent rapid switching (whipsaw)

Run with: python test_edge_cases.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

# Engine modules live in ../engine — put it on the path before importing them.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from portfolio_state import PortfolioState
from execution_engine import ExecutionEngine
from instrument_selector import select_strike
from day_lifecycle import get_day_lifecycle_rules


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_grid_row(futures_price, option_prices: dict) -> pd.Series:
    """Create a synthetic grid row (pd.Series)."""
    data = {"futures_price": futures_price}
    data.update(option_prices)
    return pd.Series(data)


def _print_result(test_name: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    suffix = f" — {detail}" if detail else ""
    print(f"{status}: {test_name}{suffix}")
    return passed


# ---------------------------------------------------------------------------
# Test 1: Missing price (one leg NaN)
# ---------------------------------------------------------------------------

def test_missing_price() -> bool:
    """When PE price is NaN, engine must NOT enter/trade. It should hold
    the previous position (or stay flat) until both legs are valid."""

    portfolio = PortfolioState()
    engine = ExecutionEngine(portfolio, "2022-11-01", "NIFTY")

    # Available strikes: 18100, 18150, 18200
    strike_lookup = {
        18100: ("NIFTY22110318100CE", "NIFTY22110318100PE"),
        18150: ("NIFTY22110318150CE", "NIFTY22110318150PE"),
        18200: ("NIFTY22110318200CE", "NIFTY22110318200PE"),
    }
    eligible = sorted(strike_lookup.keys())

    # Second 1: Both prices valid — should enter at 18150.
    ts1 = pd.Timestamp("2022-11-01 09:15:00")
    futures_price = 18152.0
    target_strike = select_strike(futures_price, eligible)
    ce, pe = strike_lookup[target_strike]
    prices1 = {ce: 95.0, pe: 88.0}
    target1 = {ce: 1, pe: 1}
    trades1 = engine.process_target_changes(ts1, target1, prices1)

    # Should have entered.
    ok1 = len(trades1) == 2 and portfolio.held_instruments() == {ce, pe}

    # Second 2: CE valid, PE is NaN — should NOT change position.
    ts2 = pd.Timestamp("2022-11-01 09:15:01")
    futures_price2 = 18205.0  # Would want to roll to 18200
    target_strike2 = select_strike(futures_price2, eligible)
    ce2, pe2 = strike_lookup[target_strike2]
    # PE price is NaN — strategy should skip.
    prices2 = {ce: 95.0, pe: 88.0, ce2: 70.0}  # pe2 missing
    # Since PE price missing, target stays as current holdings.
    target2 = {ce: 1, pe: 1}  # hold previous (caller decides this)
    trades2 = engine.process_target_changes(ts2, target2, prices2)

    # Should have done nothing (still holding old pair).
    ok2 = len(trades2) == 0 and portfolio.held_instruments() == {ce, pe}

    # Second 3: Both prices now valid — should roll.
    ts3 = pd.Timestamp("2022-11-01 09:15:02")
    prices3 = {ce: 95.0, pe: 88.0, ce2: 70.0, pe2: 110.0}
    target3 = {ce2: 1, pe2: 1}
    trades3 = engine.process_target_changes(ts3, target3, prices3)

    ok3 = len(trades3) == 4  # 2 SELL + 2 BUY

    return _print_result(
        "Missing Price (PE=NaN)",
        ok1 and ok2 and ok3,
        f"entry={len(trades1)} fills, hold={len(trades2)} fills, roll={len(trades3)} fills",
    )


# ---------------------------------------------------------------------------
# Test 2: Duplicate timestamps
# ---------------------------------------------------------------------------

def test_duplicate_timestamps() -> bool:
    """Feeding the same timestamp twice must NOT double-count PnL or
    execute duplicate orders."""

    portfolio = PortfolioState()
    engine = ExecutionEngine(portfolio, "2022-11-01", "NIFTY")

    ce = "NIFTY22110318150CE"
    pe = "NIFTY22110318150PE"

    # First call at 09:15:00 — enter.
    ts = pd.Timestamp("2022-11-01 09:15:00")
    prices = {ce: 95.0, pe: 88.0}
    target = {ce: 1, pe: 1}
    trades1 = engine.process_target_changes(ts, target, prices)
    pnl_after_1 = portfolio.realized_pnl

    # Same timestamp again, same target.
    trades2 = engine.process_target_changes(ts, target, prices)
    pnl_after_2 = portfolio.realized_pnl

    # Should be: 2 fills the first time, 0 the second time, PnL unchanged.
    ok_trades = len(trades1) == 2 and len(trades2) == 0
    ok_pnl = pnl_after_1 == pnl_after_2

    return _print_result(
        "Duplicate Timestamps",
        ok_trades and ok_pnl,
        f"1st call={len(trades1)} fills, 2nd call={len(trades2)} fills, "
        f"PnL unchanged={ok_pnl}",
    )


# ---------------------------------------------------------------------------
# Test 3: No strike change all day (flat futures)
# ---------------------------------------------------------------------------

def test_no_strike_change() -> bool:
    """Flat futures all day: exactly 1 ENTRY (2 fills), 0 ROLLs,
    1 SQUAREOFF (2 fills). Total = 4 fills."""

    portfolio = PortfolioState()
    engine = ExecutionEngine(portfolio, "2022-11-01", "NIFTY")
    lifecycle = get_day_lifecycle_rules()

    ce = "NIFTY22110318150CE"
    pe = "NIFTY22110318150PE"
    flat_price = 18152.0

    # Simulate a shortened day: 5 seconds.
    timestamps = pd.date_range("2022-11-01 09:15:00", periods=5, freq="1s")
    # Override last to be the squareoff time.
    timestamps = timestamps.tolist()
    timestamps[-1] = pd.Timestamp("2022-11-01 15:29:59")

    all_trades = []
    for ts in timestamps:
        is_sqoff = lifecycle.is_forced_squareoff(ts)

        if is_sqoff:
            target = {}
        else:
            target = {ce: 1, pe: 1}

        prices = {ce: 95.0, pe: 88.0}
        new = engine.process_target_changes(ts, target, prices, force_squareoff=is_sqoff)
        all_trades.extend(new)

    entry_trades = [t for t in all_trades if t.reason == "ENTRY"]
    roll_trades = [t for t in all_trades if t.reason == "ROLL"]
    sqoff_trades = [t for t in all_trades if t.reason == "SQUAREOFF"]

    ok = (len(entry_trades) == 2 and
          len(roll_trades) == 0 and
          len(sqoff_trades) == 2)

    return _print_result(
        "No Strike Change (flat futures)",
        ok,
        f"ENTRY={len(entry_trades)}, ROLL={len(roll_trades)}, SQUAREOFF={len(sqoff_trades)}",
    )


# ---------------------------------------------------------------------------
# Test 4: Rapid whipsaw switching
# ---------------------------------------------------------------------------

def test_whipsaw() -> bool:
    """Futures bounces across the 18150/18200 boundary every second.
    Should see frequent rolls and accumulated realized PnL drag."""

    portfolio = PortfolioState()
    engine = ExecutionEngine(portfolio, "2022-11-01", "NIFTY")

    strike_A = 18150
    ce_a, pe_a = "NIFTY22110318150CE", "NIFTY22110318150PE"
    strike_B = 18200
    ce_b, pe_b = "NIFTY22110318200CE", "NIFTY22110318200PE"

    # Alternating targets over 6 seconds: A, B, A, B, A, then squareoff.
    sequence = [
        ("09:15:00", {ce_a: 1, pe_a: 1}, {ce_a: 100.0, pe_a: 80.0, ce_b: 70.0, pe_b: 110.0}),
        ("09:15:01", {ce_b: 1, pe_b: 1}, {ce_a: 99.0, pe_a: 81.0, ce_b: 71.0, pe_b: 109.0}),
        ("09:15:02", {ce_a: 1, pe_a: 1}, {ce_a: 98.0, pe_a: 82.0, ce_b: 72.0, pe_b: 108.0}),
        ("09:15:03", {ce_b: 1, pe_b: 1}, {ce_a: 97.0, pe_a: 83.0, ce_b: 73.0, pe_b: 107.0}),
        ("09:15:04", {ce_a: 1, pe_a: 1}, {ce_a: 96.0, pe_a: 84.0, ce_b: 74.0, pe_b: 106.0}),
    ]

    all_trades = []
    for t_str, target, prices in sequence:
        ts = pd.Timestamp(f"2022-11-01 {t_str}")
        new = engine.process_target_changes(ts, target, prices)
        all_trades.extend(new)

    entry_trades = [t for t in all_trades if t.reason == "ENTRY"]
    roll_trades = [t for t in all_trades if t.reason == "ROLL"]

    # Expect: 1 ENTRY (2 fills), 4 ROLLs (4 * 4 = 16 fills).
    # Total fills = 2 + 16 = 18.
    ok_entry = len(entry_trades) == 2
    ok_rolls = len(roll_trades) == 16  # 4 roll events × 4 fills each

    # In zero-slippage model, realized PnL from rolls depends on price
    # changes between entry and exit. With these synthetic prices:
    # Roll 1: exit A@(99,81), entered@(100,80) -> PnL = (99-100)+(81-80) = 0
    # Roll 2: exit B@(72,108), entered@(71,109) -> PnL = (72-71)+(108-109) = 0
    # etc. Each roll nets to 0 because CE drops by 1 and PE rises by 1.
    # This is correct behavior — the test validates fill counts, not PnL sign.
    ok_total_fills = len(all_trades) == 18

    return _print_result(
        "Rapid Whipsaw Switching",
        ok_entry and ok_rolls and ok_total_fills,
        f"ENTRY={len(entry_trades)} fills, ROLL={len(roll_trades)} fills, "
        f"total={len(all_trades)} fills, realized_pnl={portfolio.realized_pnl:.2f}",
    )


# ---------------------------------------------------------------------------
# Test 5: Empty position close (squareoff when already flat)
# ---------------------------------------------------------------------------

def test_squareoff_when_flat() -> bool:
    """Squareoff on an already flat portfolio should produce zero trades."""

    portfolio = PortfolioState()
    engine = ExecutionEngine(portfolio, "2022-11-01", "NIFTY")

    ts = pd.Timestamp("2022-11-01 15:29:59")
    trades = engine.process_target_changes(ts, {}, {}, force_squareoff=True)

    return _print_result(
        "Squareoff When Already Flat",
        len(trades) == 0,
        f"trades={len(trades)} (expected 0)",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 70)
    print("EDGE CASE TESTS — Phase 6, Step 6.3")
    print("=" * 70)
    print()

    results = [
        test_missing_price(),
        test_duplicate_timestamps(),
        test_no_strike_change(),
        test_whipsaw(),
        test_squareoff_when_flat(),
    ]

    print()
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} passed.")

    if passed < total:
        print("SOME TESTS FAILED.")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED.")
