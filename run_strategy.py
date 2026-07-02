"""
run_strategy.py — Canonical entry point: run one or all strategies end-to-end.

The market-data layer (futures load, filtered universe, 1-second grids, strike
map) is strategy-independent, so it is built ONCE and reused across every
strategy. Each strategy's outputs are written to:

    results/strategies/<strategy_key>/
        trades.csv
        positions_timeline.csv
        mtm_timeline.csv
        daily_summary.csv

The default strategy's outputs are also mirrored to results/ root for backward
compatibility with the notebook and older tooling.

Usage
-----
    python run_strategy.py --all
    python run_strategy.py --strategy closest_strike_straddle
    python run_strategy.py --strategy farthest_strike_straddle --strategy atm_open_hold_straddle
    python run_strategy.py --list
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

import pandas as pd

from futures_loader import load_all_futures
from filtered_option_universe import build_filtered_option_universe
from second_grid_builder import build_all_second_grids
from strike_map import build_strike_map
from backtest_runner import run_full_backtest
from reporting import enrich_trades, build_daily_summary
from strategies import get_registry

logger = logging.getLogger(__name__)

from data_paths import resolve_data_root

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_ROOT = resolve_data_root(SCRIPT_DIR)
RESULTS_DIR = SCRIPT_DIR / "results"
STRATEGIES_RESULTS_DIR = RESULTS_DIR / "strategies"
DEFAULT_STRATEGY = "closest_strike_straddle"

_FOLDER_RE = re.compile(r"^NSE_(\d{8})$")


def discover_trade_dates() -> list[str]:
    dates = []
    for d in sorted(DATA_ROOT.iterdir()):
        m = _FOLDER_RE.match(d.name)
        if m and d.is_dir():
            raw = m.group(1)
            dates.append(f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}")
    return dates


def build_market_data(trade_dates):
    """Build the strategy-independent market-data layer once."""
    logger.info("Loading futures...")
    futures_store = load_all_futures(DATA_ROOT, trade_dates)

    logger.info("Loading filtered option universe...")
    meta = pd.read_csv(RESULTS_DIR / "option_metadata.csv", dtype=str)
    expiry = pd.read_csv(RESULTS_DIR / "nearest_expiry.csv", dtype=str)
    universe = build_filtered_option_universe(meta, expiry)

    logger.info("Building 1-second grids (this takes ~2 min)...")
    grids = build_all_second_grids(trade_dates, futures_store, universe, DATA_ROOT)

    logger.info("Building strike map...")
    smap = build_strike_map(universe)
    return grids, smap


def run_one_strategy(strategy_key, trade_dates, grids, smap, mirror_to_root=False):
    """Run a single strategy and write its four output CSVs."""
    logger.info("=== Running strategy: %s ===", strategy_key)
    trades_df, mtm_df, positions_df = run_full_backtest(
        trade_dates, grids, smap, strategy_key=strategy_key,
    )

    trades_df = enrich_trades(trades_df)
    summary_df = build_daily_summary(trades_df, mtm_df, positions_df)

    out_dir = STRATEGIES_RESULTS_DIR / strategy_key
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_outputs(out_dir, trades_df, positions_df, mtm_df, summary_df)
    logger.info("Wrote %d trades, %d positions, %d mtm rows -> %s",
                len(trades_df), len(positions_df), len(mtm_df), out_dir)

    if mirror_to_root:
        _write_outputs(RESULTS_DIR, trades_df, positions_df, mtm_df, summary_df)
        logger.info("Mirrored default strategy outputs to results/ root.")

    # Quick PnL headline.
    total = summary_df["gross_pnl"].sum()
    logger.info("[%s] month total PnL = %.2f across %d (date,underlier) rows.",
                strategy_key, total, len(summary_df))
    return trades_df, mtm_df, positions_df, summary_df


def _write_outputs(out_dir: Path, trades_df, positions_df, mtm_df, summary_df):
    trades_df.to_csv(out_dir / "trades.csv", index=False)
    positions_df.to_csv(out_dir / "positions_timeline.csv", index=False)
    mtm_df.to_csv(out_dir / "mtm_timeline.csv", index=False)
    summary_df.to_csv(out_dir / "daily_summary.csv", index=False)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s",
                        stream=sys.stdout)

    registry = get_registry()
    parser = argparse.ArgumentParser(description="Run backtest strategies.")
    parser.add_argument("--strategy", action="append", default=[],
                        help="Strategy key to run (repeatable). Omit with --all.")
    parser.add_argument("--all", action="store_true", help="Run every registered strategy.")
    parser.add_argument("--list", action="store_true", help="List strategies and exit.")
    args = parser.parse_args()

    if args.list:
        print("Registered strategies:")
        for key, info in registry.items():
            print(f"  {key:32} {info.name}")
        return

    if args.all or not args.strategy:
        keys = list(registry.keys())
    else:
        keys = args.strategy
        unknown = [k for k in keys if k not in registry]
        if unknown:
            parser.error(f"Unknown strategy key(s): {unknown}. "
                         f"Available: {sorted(registry)}")

    trade_dates = discover_trade_dates()
    print("=" * 70)
    print(f"RUNNING {len(keys)} STRATEGY(S) OVER {len(trade_dates)} TRADING DAYS")
    print("Strategies:", ", ".join(keys))
    print("=" * 70)

    grids, smap = build_market_data(trade_dates)

    for key in keys:
        run_one_strategy(key, trade_dates, grids, smap,
                         mirror_to_root=(key == DEFAULT_STRATEGY))

    print("\nDone. Outputs in results/strategies/<key>/.")


if __name__ == "__main__":
    main()
