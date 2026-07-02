"""
test_phase4.py — Combined tests for Phase 4 (Steps 4.1, 4.2, 4.3).

Runs:
  1. Strategy target-position tests (Step 4.1) — with real data for one day
  2. Day lifecycle rule tests (Step 4.2) — simulated sequence
  3. Order generator tests (Step 4.3) — three scenarios
"""

import sys
import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
    stream=sys.stdout,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))
from data_paths import resolve_data_root, results_dir
DATA_ROOT = resolve_data_root()
RESULTS_DIR = results_dir()


# ===================================================================
# STEP 4.1 — Strategy target-position tests
# ===================================================================

def test_strategy():
    from futures_loader import load_all_futures
    from filtered_option_universe import build_filtered_option_universe
    from second_grid_builder import build_all_second_grids
    from strike_map import build_strike_map, get_eligible_strikes
    from strategy import ClosestStrikeLongStraddleStrategy, MarketState

    TEST_DATE = "2022-11-01"
    TEST_UNDERLIER = "NIFTY"

    print("=" * 70)
    print("STEP 4.1 — STRATEGY TARGET-POSITION TEST")
    print("=" * 70)

    # Load one day's data.
    print("Loading data for one day...")
    futures_store = load_all_futures(DATA_ROOT, [TEST_DATE])
    meta = pd.read_csv(RESULTS_DIR / "option_metadata.csv", dtype=str)
    expiry = pd.read_csv(RESULTS_DIR / "nearest_expiry.csv", dtype=str)
    universe = build_filtered_option_universe(meta, expiry)
    grids = build_all_second_grids([TEST_DATE], futures_store, universe, DATA_ROOT)
    grid = grids[(TEST_DATE, TEST_UNDERLIER)]

    smap = build_strike_map(universe)
    _, strike_lookup = get_eligible_strikes(smap, TEST_DATE, TEST_UNDERLIER)

    # Instantiate strategy.
    strat = ClosestStrikeLongStraddleStrategy()

    sample_times = ["09:15:00", "09:30:00", "12:00:00", "14:00:00", "15:29:59"]

    print(f"\n{'timestamp':<22} {'target_positions'}")
    print("-" * 75)

    for t_str in sample_times:
        ts = pd.Timestamp(f"{TEST_DATE} {t_str}")
        row = grid.loc[ts]

        ms = MarketState(
            trade_date=TEST_DATE,
            underlier=TEST_UNDERLIER,
            timestamp=ts,
            grid_row=row,
            strike_lookup=strike_lookup,
        )

        target = strat.get_target_positions(ts, ms)
        # Format output.
        if target:
            instrs = ", ".join(f"{k}=1" for k in sorted(target.keys()))
            print(f"{str(ts):<22} {{{instrs}}}")
        else:
            print(f"{str(ts):<22} {{}}  (flat)")

    print()


# ===================================================================
# STEP 4.2 — Day lifecycle rule tests
# ===================================================================

def test_lifecycle():
    from day_lifecycle import get_day_lifecycle_rules

    print("=" * 70)
    print("STEP 4.2 — DAY LIFECYCLE RULE TESTS")
    print("=" * 70)

    rules = get_day_lifecycle_rules()
    TEST_DATE = "2022-11-01"

    # Simulated sequence of (timestamp, current_pair, target_pair).
    pair_A = (18150, "NIFTY22110318150CE", "NIFTY22110318150PE")
    pair_B = (18200, "NIFTY22110318200CE", "NIFTY22110318200PE")

    sequence = [
        ("09:15:00", None,   pair_A),   # session start, no holdings -> ENTRY
        ("09:15:01", pair_A, pair_A),   # same strike -> HOLD
        ("09:30:00", pair_A, pair_A),   # same strike -> HOLD
        ("10:00:00", pair_A, pair_B),   # different strike -> ROLL
        ("10:00:01", pair_B, pair_B),   # same strike -> HOLD
        ("12:00:00", pair_B, pair_B),   # same strike -> HOLD
        ("15:29:58", pair_B, pair_B),   # one second before close -> HOLD
        ("15:29:59", pair_B, pair_B),   # FORCED SQUAREOFF (override target to flat)
    ]

    all_passed = True

    print(f"\n{'timestamp':<14} {'session_start':>14} {'hold':>6} {'squareoff':>11} {'action'}")
    print("-" * 65)

    for t_str, current, target in sequence:
        ts = pd.Timestamp(f"{TEST_DATE} {t_str}")
        is_start = rules.is_session_start(ts)
        hold = rules.should_hold_position(current, target)
        is_sqoff = rules.is_forced_squareoff(ts)

        # Determine expected action.
        if is_sqoff:
            action = "SQUAREOFF"
        elif is_start and current is None:
            action = "ENTRY"
        elif hold:
            action = "HOLD"
        else:
            action = "ROLL"

        print(f"{t_str:<14} {str(is_start):>14} {str(hold):>6} {str(is_sqoff):>11} {action}")

    # Explicit assertions.
    ts_start = pd.Timestamp(f"{TEST_DATE} 09:15:00")
    ts_mid = pd.Timestamp(f"{TEST_DATE} 12:00:00")
    ts_end = pd.Timestamp(f"{TEST_DATE} 15:29:59")

    checks = [
        ("is_session_start(09:15:00) == True",
         rules.is_session_start(ts_start) is True),
        ("is_session_start(12:00:00) == False",
         rules.is_session_start(ts_mid) is False),
        ("is_forced_squareoff(15:29:59) == True",
         rules.is_forced_squareoff(ts_end) is True),
        ("is_forced_squareoff(12:00:00) == False",
         rules.is_forced_squareoff(ts_mid) is False),
        ("should_hold(pair_A, pair_A) == True",
         rules.should_hold_position(pair_A, pair_A) is True),
        ("should_hold(pair_A, pair_B) == False",
         rules.should_hold_position(pair_A, pair_B) is False),
        ("should_hold(None, pair_A) == False",
         rules.should_hold_position(None, pair_A) is False),
    ]

    print()
    for label, result in checks:
        status = "PASS" if result else "FAIL"
        if not result:
            all_passed = False
        print(f"{status}: {label}")

    print()
    return all_passed


# ===================================================================
# STEP 4.3 — Order generator tests
# ===================================================================

def test_order_generator():
    from order_generator import generate_orders

    print("=" * 70)
    print("STEP 4.3 — ORDER GENERATOR TESTS")
    print("=" * 70)

    ts = pd.Timestamp("2022-11-01 09:15:00")
    all_passed = True

    # --- Scenario A: Initial entry (empty -> 2 instruments) ----------------
    current_a = {}
    target_a = {"NIFTY22110318150CE": 1, "NIFTY22110318150PE": 1}
    orders_a = generate_orders(current_a, target_a, ts)

    sells_a = [o for o in orders_a if o.direction == "SELL"]
    buys_a = [o for o in orders_a if o.direction == "BUY"]

    ok_a = len(sells_a) == 0 and len(buys_a) == 2
    if not ok_a:
        all_passed = False
    print(f"{'PASS' if ok_a else 'FAIL'}: Scenario A (ENTRY) -> "
          f"{len(sells_a)} SELL + {len(buys_a)} BUY")
    for o in orders_a:
        print(f"  {o.direction:>4} {o.instrument_name}")

    # --- Scenario B: Roll (2 old -> 2 new) ---------------------------------
    current_b = {"NIFTY22110318150CE": 1, "NIFTY22110318150PE": 1}
    target_b = {"NIFTY22110318200CE": 1, "NIFTY22110318200PE": 1}
    orders_b = generate_orders(current_b, target_b, ts)

    sells_b = [o for o in orders_b if o.direction == "SELL"]
    buys_b = [o for o in orders_b if o.direction == "BUY"]

    # Check SELL before BUY ordering.
    sell_indices = [i for i, o in enumerate(orders_b) if o.direction == "SELL"]
    buy_indices = [i for i, o in enumerate(orders_b) if o.direction == "BUY"]
    sell_before_buy = all(s < b for s in sell_indices for b in buy_indices)

    ok_b = len(sells_b) == 2 and len(buys_b) == 2 and sell_before_buy
    if not ok_b:
        all_passed = False
    print(f"\n{'PASS' if ok_b else 'FAIL'}: Scenario B (ROLL) -> "
          f"{len(sells_b)} SELL + {len(buys_b)} BUY, "
          f"SELL-before-BUY={'Yes' if sell_before_buy else 'No'}")
    for o in orders_b:
        print(f"  {o.direction:>4} {o.instrument_name}")

    # --- Scenario C: Forced squareoff (2 held -> empty) --------------------
    current_c = {"NIFTY22110318200CE": 1, "NIFTY22110318200PE": 1}
    target_c = {}
    orders_c = generate_orders(current_c, target_c, ts)

    sells_c = [o for o in orders_c if o.direction == "SELL"]
    buys_c = [o for o in orders_c if o.direction == "BUY"]

    ok_c = len(sells_c) == 2 and len(buys_c) == 0
    if not ok_c:
        all_passed = False
    print(f"\n{'PASS' if ok_c else 'FAIL'}: Scenario C (SQUAREOFF) -> "
          f"{len(sells_c)} SELL + {len(buys_c)} BUY")
    for o in orders_c:
        print(f"  {o.direction:>4} {o.instrument_name}")

    # --- Scenario D: No change (hold) -> zero orders ----------------------
    current_d = {"NIFTY22110318200CE": 1, "NIFTY22110318200PE": 1}
    target_d = {"NIFTY22110318200CE": 1, "NIFTY22110318200PE": 1}
    orders_d = generate_orders(current_d, target_d, ts)

    ok_d = len(orders_d) == 0
    if not ok_d:
        all_passed = False
    print(f"\n{'PASS' if ok_d else 'FAIL'}: Scenario D (HOLD) -> "
          f"{len(orders_d)} orders (expected 0)")

    print()
    return all_passed


# ===================================================================
# MAIN
# ===================================================================

if __name__ == "__main__":
    print()

    # Run order generator tests first (fastest, no data loading).
    ok_orders = test_order_generator()

    # Run lifecycle tests (pure logic, no data loading).
    ok_lifecycle = test_lifecycle()

    # Run strategy tests (loads one day of real data).
    test_strategy()

    print("=" * 70)
    print("PHASE 4 TEST SUMMARY")
    print("=" * 70)
    print(f"Step 4.1 (Strategy)        : smoke test complete (see output above)")
    print(f"Step 4.2 (Lifecycle rules)  : {'ALL PASSED' if ok_lifecycle else 'SOME FAILED'}")
    print(f"Step 4.3 (Order generator)  : {'ALL PASSED' if ok_orders else 'SOME FAILED'}")
    print("\nDone.")
