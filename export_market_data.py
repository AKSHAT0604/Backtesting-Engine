"""
export_market_data.py — Deployment prep: precompute the two raw-data-dependent
Day Drilldown charts (futures price, held-leg option price) as Parquet, so they
work on Streamlit Community Cloud without Data/allData being present.

Produces:
    results/futures_intraday.parquet
        [trade_date, underlier, timestamp, price] for every trading day, both
        underliers -- strategy-independent (identical futures ticks regardless
        of which strategy is selected).
    results/strategies/<key>/held_leg_prices.parquet
        [trade_date, underlier, option_type, timestamp, price] -- the CE/PE
        price actually held at each second, stitched across every roll that
        day, per strategy. Mirrors the on-the-fly computation
        dashboard/pages/1_Day_Drilldown.py used to do against raw ticks.

Requires the raw dataset (Data/allData/) locally -- run this once wherever the
raw data lives; only the (much smaller) Parquet outputs get committed.

Usage:
    python export_market_data.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "engine"))
from data_paths import resolve_data_root, results_dir  # noqa: E402
from futures_loader import load_all_futures, load_futures_file  # noqa: E402
from strategies import get_registry  # noqa: E402

_FOLDER_RE = re.compile(r"^NSE_(\d{8})$")


def discover_trade_dates(data_root: Path) -> list[str]:
    dates = []
    for d in sorted(data_root.iterdir()):
        m = _FOLDER_RE.match(d.name)
        if m and d.is_dir():
            raw = m.group(1)
            dates.append(f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}")
    return dates


def export_futures(data_root: Path, trade_dates: list[str], out_path: Path) -> None:
    store = load_all_futures(data_root, trade_dates)
    parts = [df[["trade_date", "underlier", "timestamp", "price"]]
             for df in store.values() if not df.empty]
    combined = pd.concat(parts, ignore_index=True)
    combined.to_parquet(out_path, engine="pyarrow", compression="snappy", index=False)
    print(f"  futures_intraday.parquet: {len(combined):,} rows -> {out_path.stat().st_size / 1e6:.1f} MB")


def export_held_leg_prices(data_root: Path, strategy_key: str, positions_path: Path, out_path: Path) -> None:
    positions = pd.read_csv(positions_path)
    positions["timestamp"] = pd.to_datetime(positions["timestamp"])
    holding = positions[positions["state"] == "HOLDING"].sort_values(
        ["trade_date", "underlier", "timestamp"]
    ).copy()
    holding["next_timestamp"] = holding.groupby(["trade_date", "underlier"])["timestamp"].shift(-1)

    tick_cache: dict[tuple[str, str], pd.DataFrame] = {}

    def _instrument_ticks(trade_date: str, instrument: str) -> pd.DataFrame:
        key = (trade_date, instrument)
        if key not in tick_cache:
            folder = "NSE_" + trade_date.replace("-", "")
            path = data_root / folder / "Options" / f"{instrument}.csv"
            if path.is_file():
                tick_cache[key] = load_futures_file(path, trade_date, instrument)[["timestamp", "price"]]
            else:
                tick_cache[key] = pd.DataFrame(columns=["timestamp", "price"])
        return tick_cache[key]

    rows = []
    for _, row in holding.iterrows():
        end = row["next_timestamp"] if pd.notna(row["next_timestamp"]) else pd.Timestamp.max
        for leg_col, leg_type in (("ce_instrument", "CE"), ("pe_instrument", "PE")):
            instrument = row[leg_col]
            if pd.isna(instrument):
                continue
            ticks = _instrument_ticks(row["trade_date"], instrument)
            seg = ticks[(ticks["timestamp"] >= row["timestamp"]) & (ticks["timestamp"] < end)]
            if seg.empty:
                continue
            seg = seg.copy()
            seg["trade_date"] = row["trade_date"]
            seg["underlier"] = row["underlier"]
            seg["option_type"] = leg_type
            rows.append(seg[["trade_date", "underlier", "option_type", "timestamp", "price"]])

    combined = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["trade_date", "underlier", "option_type", "timestamp", "price"])
    combined.to_parquet(out_path, engine="pyarrow", compression="snappy", index=False)
    print(f"  {strategy_key}/held_leg_prices.parquet: {len(combined):,} rows -> "
          f"{out_path.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    RESULTS_DIR = results_dir()
    DATA_ROOT = resolve_data_root()
    if not DATA_ROOT.is_dir():
        print(f"ERROR: raw dataset not found at {DATA_ROOT}. Run this where Data/allData exists.")
        sys.exit(1)

    trade_dates = discover_trade_dates(DATA_ROOT)
    print("=" * 70)
    print(f"EXPORTING MARKET DATA FOR DEPLOYMENT ({len(trade_dates)} trading days)")
    print("=" * 70)

    print("\nFutures (shared across strategies):")
    export_futures(DATA_ROOT, trade_dates, RESULTS_DIR / "futures_intraday.parquet")

    print("\nHeld CE/PE leg prices (per strategy):")
    registry = get_registry()
    for key in registry:
        strat_dir = RESULTS_DIR / "strategies" / key
        positions_csv = strat_dir / "positions_timeline.csv"
        if not positions_csv.is_file():
            print(f"  {key}: no positions_timeline.csv, skipping.")
            continue
        export_held_leg_prices(DATA_ROOT, key, positions_csv, strat_dir / "held_leg_prices.parquet")

    print("\nDone.")
