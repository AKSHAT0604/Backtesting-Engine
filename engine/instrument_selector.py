"""
instrument_selector.py — Phase 3, Steps 3.2 & 3.3: Strike selection and
target instrument resolution.

Exports:
    select_strike(futures_price, available_strikes) -> int | float | None
    get_target_pair(trade_date, underlier, timestamp, second_grid_df, strike_lookup)
        -> (strike, ce_instrument, pe_instrument) | (None, None, None)

Governed by:
    SPEC.md Rule 8   — closest strike to futures price
    ASSUMPTIONS.md A6 — tie-break: lower strike wins
    ASSUMPTIONS.md A5 — both CE and PE must have a valid price to enter
"""

import logging
import math

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Step 3.2 — Pure closest-strike selector
# ---------------------------------------------------------------------------

def select_strike(
    futures_price: float | None,
    available_strikes: list[int | float],
) -> int | float | None:
    """Return the closest strike to futures_price from available_strikes.

    Tie-break rule (A6): if two strikes are exactly equidistant, the lower
    strike is chosen.

    Parameters
    ----------
    futures_price : float or None
        Current futures price. Returns None if NaN/None.
    available_strikes : list
        Sorted ascending list of eligible strike values (both legs present).
        Returns None if empty.

    Returns
    -------
    int | float | None
        The selected strike, or None if selection is impossible.
    """
    if futures_price is None or (isinstance(futures_price, float) and math.isnan(futures_price)):
        return None

    if not available_strikes:
        return None

    best_strike = available_strikes[0]
    best_dist = abs(futures_price - best_strike)

    for strike in available_strikes[1:]:
        dist = abs(futures_price - strike)
        if dist < best_dist:
            best_dist = dist
            best_strike = strike
        # If dist == best_dist, we keep the earlier (lower) strike — tie-break.
        # Since available_strikes is sorted ascending, the first match at a
        # given distance is already the lower strike, so no action needed.

    return best_strike


# ---------------------------------------------------------------------------
# Step 3.3 — Target instrument pair resolver
# ---------------------------------------------------------------------------

def get_target_pair(
    trade_date: str,
    underlier: str,
    timestamp: pd.Timestamp,
    second_grid_df: pd.DataFrame,
    strike_lookup: dict[int | float, tuple[str, str]],
) -> tuple[int | float | None, str | None, str | None]:
    """Resolve the target CE/PE instruments at a given timestamp.

    Parameters
    ----------
    trade_date : str
        For logging only.
    underlier : str
        For logging only.
    timestamp : pd.Timestamp
        The second to evaluate.
    second_grid_df : pd.DataFrame
        Wide grid from build_second_grid, indexed by timestamp.
        Must contain a "futures_price" column and one column per instrument.
    strike_lookup : dict
        Maps strike -> (ce_instrument_name, pe_instrument_name).
        From get_eligible_strikes.

    Returns
    -------
    (selected_strike, ce_instrument_name, pe_instrument_name)
        All None if selection fails for any reason.
    """
    NONE_RESULT = (None, None, None)

    # ---- 1. Read futures price from the grid ------------------------------
    if timestamp not in second_grid_df.index:
        logger.debug("[%s] %s @ %s: timestamp not in grid.", trade_date, underlier, timestamp)
        return NONE_RESULT

    futures_price = second_grid_df.at[timestamp, "futures_price"]

    # ---- 2. Select the closest strike -------------------------------------
    available_strikes = sorted(strike_lookup.keys())
    selected_strike = select_strike(futures_price, available_strikes)

    if selected_strike is None:
        logger.debug(
            "[%s] %s @ %s: no strike selected (futures_price=%s).",
            trade_date, underlier, timestamp, futures_price,
        )
        return NONE_RESULT

    ce_instr, pe_instr = strike_lookup[selected_strike]

    # ---- 3. Verify both legs have a non-NaN price at this second (A5) -----
    ce_price_available = (
        ce_instr in second_grid_df.columns
        and pd.notna(second_grid_df.at[timestamp, ce_instr])
    )
    pe_price_available = (
        pe_instr in second_grid_df.columns
        and pd.notna(second_grid_df.at[timestamp, pe_instr])
    )

    if not ce_price_available or not pe_price_available:
        logger.debug(
            "[%s] %s @ %s: strike %s selected but leg price missing "
            "(CE=%s PE=%s). Skipping.",
            trade_date, underlier, timestamp, selected_strike,
            "OK" if ce_price_available else "NaN",
            "OK" if pe_price_available else "NaN",
        )
        return NONE_RESULT

    return (selected_strike, ce_instr, pe_instr)


# ---------------------------------------------------------------------------
# Unit tests for select_strike (Step 3.2)
# ---------------------------------------------------------------------------

def _run_unit_tests() -> bool:
    print("=" * 70)
    print("UNIT TESTS — select_strike")
    print("=" * 70)

    all_passed = True

    # Test 1: clear single closest strike
    result = select_strike(18150.0, [17900, 18000, 18100, 18150, 18200, 18300])
    expected = 18150
    status = "PASS" if result == expected else "FAIL"
    if result != expected:
        all_passed = False
    print(f"{status}: T1 exact match   -> select_strike(18150, [...]) = {result}  (expected {expected})")

    # Test 2: exact tie — lower strike wins (A6)
    result = select_strike(18175.0, [18000, 18100, 18150, 18200, 18300])
    expected = 18150  # 18150 and 18200 are both 25 away; lower wins
    status = "PASS" if result == expected else "FAIL"
    if result != expected:
        all_passed = False
    print(f"{status}: T2 tie-break      -> select_strike(18175, [...]) = {result}  (expected {expected})")

    # Test 3: futures_price equals one of the strikes
    result = select_strike(18200.0, [18000, 18100, 18200, 18300, 18400])
    expected = 18200
    status = "PASS" if result == expected else "FAIL"
    if result != expected:
        all_passed = False
    print(f"{status}: T3 on-strike      -> select_strike(18200, [...]) = {result}  (expected {expected})")

    # Test 4: empty available_strikes
    result = select_strike(18200.0, [])
    expected = None
    status = "PASS" if result == expected else "FAIL"
    if result != expected:
        all_passed = False
    print(f"{status}: T4 empty list     -> select_strike(18200, []) = {result}  (expected {expected})")

    # Test 5a: futures at extreme low end
    result = select_strike(14000.0, [15000, 16000, 17000, 18000])
    expected = 15000
    status = "PASS" if result == expected else "FAIL"
    if result != expected:
        all_passed = False
    print(f"{status}: T5a extreme low   -> select_strike(14000, [...]) = {result}  (expected {expected})")

    # Test 5b: futures at extreme high end
    result = select_strike(20000.0, [15000, 16000, 17000, 18000])
    expected = 18000
    status = "PASS" if result == expected else "FAIL"
    if result != expected:
        all_passed = False
    print(f"{status}: T5b extreme high  -> select_strike(20000, [...]) = {result}  (expected {expected})")

    # Test 6: NaN futures price
    result = select_strike(float("nan"), [18000, 18100, 18200])
    expected = None
    status = "PASS" if result == expected else "FAIL"
    if result != expected:
        all_passed = False
    print(f"{status}: T6 NaN price      -> select_strike(NaN, [...]) = {result}  (expected {expected})")

    # Test 7: None futures price
    result = select_strike(None, [18000, 18100, 18200])
    expected = None
    status = "PASS" if result == expected else "FAIL"
    if result != expected:
        all_passed = False
    print(f"{status}: T7 None price     -> select_strike(None, [...]) = {result}  (expected {expected})")

    print()
    return all_passed


# ---------------------------------------------------------------------------
# Smoke test for get_target_pair (Step 3.3)
# ---------------------------------------------------------------------------

def _run_smoke_test():
    """Build one day's grid and test get_target_pair at several timestamps."""
    import re
    from pathlib import Path

    from futures_loader import load_all_futures
    from filtered_option_universe import build_filtered_option_universe
    from second_grid_builder import build_all_second_grids
    from strike_map import build_strike_map, get_eligible_strikes

    from data_paths import resolve_data_root, results_dir
    DATA_ROOT = resolve_data_root()
    RESULTS_DIR = results_dir()

    TEST_DATE = "2022-11-01"
    TEST_UNDERLIER = "NIFTY"

    print("=" * 70)
    print(f"SMOKE TEST — get_target_pair ({TEST_DATE}, {TEST_UNDERLIER})")
    print("=" * 70)

    # ---- Load just the one day we need ------------------------------------
    print("Loading futures for one day...")
    futures_store = load_all_futures(DATA_ROOT, [TEST_DATE])

    print("Loading filtered option universe...")
    meta = pd.read_csv(RESULTS_DIR / "option_metadata.csv", dtype=str)
    expiry = pd.read_csv(RESULTS_DIR / "nearest_expiry.csv", dtype=str)
    universe = build_filtered_option_universe(meta, expiry)

    print("Building 1-second grid for one day...")
    grids = build_all_second_grids([TEST_DATE], futures_store, universe, DATA_ROOT)
    grid = grids[(TEST_DATE, TEST_UNDERLIER)]

    print("Building strike map...")
    smap = build_strike_map(universe)
    eligible_strikes, strike_lookup = get_eligible_strikes(smap, TEST_DATE, TEST_UNDERLIER)

    print(f"\nGrid shape: {grid.shape}")
    print(f"Eligible strikes: {len(eligible_strikes)}")
    print(f"Strike lookup entries: {len(strike_lookup)}\n")

    # ---- Sample timestamps ------------------------------------------------
    sample_times = [
        "09:15:00",  # session open
        "09:15:30",  # 30 seconds in
        "09:30:00",  # 15 min in
        "10:00:00",  # 45 min in
        "12:00:00",  # midday
        "14:00:00",  # afternoon
        "15:00:00",  # last half hour
        "15:29:59",  # final second
    ]

    print(f"{'timestamp':<22} {'fut_price':>10} {'strike':>8} {'CE instrument':<26} {'PE instrument'}")
    print("-" * 95)

    for t_str in sample_times:
        ts = pd.Timestamp(f"{TEST_DATE} {t_str}")
        fut_px = grid.at[ts, "futures_price"] if ts in grid.index else float("nan")

        strike, ce, pe = get_target_pair(
            TEST_DATE, TEST_UNDERLIER, ts, grid, strike_lookup,
        )

        if strike is not None:
            print(
                f"{str(ts):<22} {fut_px:>10.2f} {int(strike):>8} "
                f"{ce:<26} {pe}"
            )
        else:
            print(f"{str(ts):<22} {fut_px:>10} {'None':>8} {'--':<26} {'--'}")

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(message)s",
        stream=sys.stdout,
    )

    tests_ok = _run_unit_tests()
    if not tests_ok:
        print("Unit tests FAILED. Aborting smoke test.")
        sys.exit(1)

    _run_smoke_test()
    print("Done.")
