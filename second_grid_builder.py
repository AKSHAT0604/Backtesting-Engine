"""
second_grid_builder.py — Constructs the uniform 1-second market-state grid.

Exports:
    build_second_grid(trade_date, underlier, futures_df, option_price_dict) -> pd.DataFrame
    build_all_second_grids(trade_dates, futures_store, filtered_universe_df, data_root) -> dict

Governed by:
    SPEC.md Rule 7   — 1-second evaluation resolution
    ASSUMPTIONS.md A1 — session 09:15:00 to 15:29:59 (22,500 seconds)
    ASSUMPTIONS.md A2 — last tick per second wins
    ASSUMPTIONS.md A3 — forward-fill missing seconds
    ASSUMPTIONS.md A4 — NaN before first tick
"""

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SESSION_START = "09:15:00"
SESSION_END = "15:29:59"
EXPECTED_ROWS = 22_500

_RAW_COLS = ["_date_str", "_time_str", "price", "volume", "open_interest"]


# ---------------------------------------------------------------------------
# Option tick loader (lightweight — only timestamp + price)
# ---------------------------------------------------------------------------

def _load_option_ticks(filepath: Path) -> pd.DataFrame | None:
    """Read an option CSV and return a deduplicated (timestamp, price) DataFrame.

    Returns None if the file is missing, empty, or unreadable.
    """
    try:
        raw = pd.read_csv(
            filepath, header=None, names=_RAW_COLS,
            dtype={"_date_str": str, "_time_str": str}, engine="c",
        )
    except Exception as exc:
        logger.debug("Failed to read %s: %s", filepath.name, exc)
        return None

    if raw.empty:
        return None

    raw["timestamp"] = pd.to_datetime(
        raw["_date_str"].str.strip() + " " + raw["_time_str"].str.strip(),
        format="%Y%m%d %H:%M:%S", errors="coerce",
    )
    raw["price"] = pd.to_numeric(raw["price"], errors="coerce")
    raw = raw[raw["timestamp"].notna() & raw["price"].notna()].copy()

    if raw.empty:
        return None

    # Sort + deduplicate: last tick per second wins (A2).
    raw.sort_values("timestamp", kind="stable", inplace=True)
    raw.drop_duplicates(subset=["timestamp"], keep="last", inplace=True)

    return raw[["timestamp", "price"]].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Core grid builder
# ---------------------------------------------------------------------------

def build_second_grid(
    trade_date: str,
    underlier: str,
    futures_df: pd.DataFrame,
    option_price_dict: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Build a wide 1-second price grid for one (trade_date, underlier).

    Parameters
    ----------
    trade_date : str
        Trading day in YYYY-MM-DD format.
    underlier : str
        "NIFTY" or "BANKNIFTY".
    futures_df : pd.DataFrame
        Cleaned futures DataFrame with columns [timestamp, price, ...].
    option_price_dict : dict[str, pd.DataFrame]
        Maps instrument_name -> DataFrame with columns [timestamp, price].
        Each is already deduplicated (last tick per second).

    Returns
    -------
    pd.DataFrame
        Index: DatetimeIndex of 22,500 seconds (09:15:00–15:29:59).
        Columns: "futures_price" + one column per instrument_name.
        Values: forward-filled prices; NaN before first tick.
    """
    # ---- Build the uniform 1-second index ---------------------------------
    day_start = pd.Timestamp(f"{trade_date} {SESSION_START}")
    day_end = pd.Timestamp(f"{trade_date} {SESSION_END}")
    grid_index = pd.date_range(start=day_start, end=day_end, freq="1s")

    assert len(grid_index) == EXPECTED_ROWS, (
        f"Grid index has {len(grid_index)} rows, expected {EXPECTED_ROWS}"
    )

    grid = pd.DataFrame(index=grid_index)
    grid.index.name = "timestamp"

    # ---- Futures price on the grid ----------------------------------------
    if futures_df is not None and not futures_df.empty:
        fut_series = (
            futures_df.set_index("timestamp")["price"]
            .reindex(grid_index)
            .ffill()
        )
        grid["futures_price"] = fut_series
    else:
        grid["futures_price"] = float("nan")

    # ---- Option prices on the grid ----------------------------------------
    for instr_name, tick_df in option_price_dict.items():
        if tick_df is None or tick_df.empty:
            grid[instr_name] = float("nan")
            continue

        opt_series = (
            tick_df.set_index("timestamp")["price"]
            .reindex(grid_index)
            .ffill()
        )
        grid[instr_name] = opt_series

    return grid


# ---------------------------------------------------------------------------
# Batch builder
# ---------------------------------------------------------------------------

def build_all_second_grids(
    trade_dates: list[str],
    futures_store: dict[tuple[str, str], pd.DataFrame],
    filtered_universe_df: pd.DataFrame,
    data_root: str | Path,
) -> dict[tuple[str, str], pd.DataFrame]:
    """Build 1-second grids for all (trade_date, underlier) pairs.

    Parameters
    ----------
    trade_dates : list[str]
        Ordered trading dates.
    futures_store : dict
        From futures_loader.load_all_futures.
    filtered_universe_df : pd.DataFrame
        From filtered_option_universe.build_filtered_option_universe.
    data_root : str | Path
        Path to Data/allData/.

    Returns
    -------
    dict[(trade_date, underlier), pd.DataFrame]
        Wide second-grid DataFrames.
    """
    data_root = Path(data_root)
    grids: dict[tuple[str, str], pd.DataFrame] = {}

    underliers = ["NIFTY", "BANKNIFTY"]

    for trade_date in trade_dates:
        folder_name = "NSE_" + trade_date.replace("-", "")
        options_dir = data_root / folder_name / "Options"

        for underlier in underliers:
            # ---- Get futures DataFrame ------------------------------------
            fut_df = futures_store.get((trade_date, underlier))

            # ---- Get eligible option instruments for this day/underlier ---
            day_opts = filtered_universe_df[
                (filtered_universe_df["trade_date"] == trade_date)
                & (filtered_universe_df["underlier"] == underlier)
            ]

            # ---- Load option tick files -----------------------------------
            option_price_dict: dict[str, pd.DataFrame | None] = {}
            for _, row in day_opts.iterrows():
                instr_name = row["instrument_name"]
                fname = row["filename"]
                filepath = options_dir / fname

                if filepath.is_file():
                    tick_df = _load_option_ticks(filepath)
                    option_price_dict[instr_name] = tick_df
                else:
                    logger.warning(
                        "[%s] %s: file not found at %s",
                        trade_date, instr_name, filepath,
                    )
                    option_price_dict[instr_name] = None

            # ---- Build the grid -------------------------------------------
            grid = build_second_grid(trade_date, underlier, fut_df, option_price_dict)
            grids[(trade_date, underlier)] = grid

            n_cols = len(grid.columns)
            mem_mb = grid.memory_usage(deep=True).sum() / (1024 * 1024)
            logger.info(
                "[%s] %s grid built: %d rows x %d cols (%.1f MB).",
                trade_date, underlier, len(grid), n_cols, mem_mb,
            )

    return grids


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(message)s",
        stream=sys.stdout,
    )

    from futures_loader import load_all_futures
    from filtered_option_universe import build_filtered_option_universe

    from data_paths import resolve_data_root
    SCRIPT_DIR = Path(__file__).resolve().parent
    DATA_ROOT = resolve_data_root(SCRIPT_DIR)
    RESULTS_DIR = SCRIPT_DIR / "results"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # ---- Discover trade dates ---------------------------------------------
    import re
    _FOLDER_RE = re.compile(r"^NSE_(\d{8})$")
    trade_dates = []
    for d in sorted(DATA_ROOT.iterdir()):
        m = _FOLDER_RE.match(d.name)
        if m and d.is_dir():
            raw = m.group(1)
            trade_dates.append(f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}")

    print("=" * 70)
    print("STEP 2.4 — 1-SECOND GRID CONSTRUCTION")
    print("=" * 70)
    print(f"Trade dates: {len(trade_dates)}\n")

    # ---- Load futures -----------------------------------------------------
    print("Loading futures...")
    futures_store = load_all_futures(DATA_ROOT, trade_dates)

    # ---- Load filtered option universe ------------------------------------
    print("Loading filtered option universe...")
    meta = pd.read_csv(RESULTS_DIR / "option_metadata.csv", dtype=str)
    expiry = pd.read_csv(RESULTS_DIR / "nearest_expiry.csv", dtype=str)
    universe = build_filtered_option_universe(meta, expiry)

    # ---- Build all grids --------------------------------------------------
    print("\nBuilding 1-second grids...\n")
    grids = build_all_second_grids(trade_dates, futures_store, universe, DATA_ROOT)

    # ---- Validation -------------------------------------------------------
    print("\n" + "=" * 70)
    print("VALIDATION")
    print("=" * 70)

    # Check 1: every grid has exactly 22,500 rows.
    all_correct = True
    for key, grid in grids.items():
        if len(grid) != EXPECTED_ROWS:
            print(f"FAIL: {key} has {len(grid)} rows, expected {EXPECTED_ROWS}")
            all_correct = False
    if all_correct:
        print(f"PASS: All {len(grids)} grids have exactly {EXPECTED_ROWS} rows.")

    # Check 2: (2022-11-01, NIFTY) futures coverage.
    sample_key = ("2022-11-01", "NIFTY")
    if sample_key in grids:
        sg = grids[sample_key]
        valid_fut = sg["futures_price"].notna().sum()
        nan_fut = sg["futures_price"].isna().sum()
        print(f"\n(2022-11-01, NIFTY) futures_price coverage:")
        print(f"  Valid (non-NaN) seconds : {valid_fut}")
        print(f"  NaN seconds (pre-tick)  : {nan_fut}")
        print(f"  Total columns           : {len(sg.columns)}")

    # Check 3: memory usage summary.
    total_mem_mb = 0.0
    summary_rows = []
    for key in sorted(grids.keys()):
        g = grids[key]
        mem = g.memory_usage(deep=True).sum() / (1024 * 1024)
        total_mem_mb += mem
        summary_rows.append({
            "trade_date": key[0],
            "underlier": key[1],
            "rows": len(g),
            "columns": len(g.columns),
            "memory_mb": round(mem, 1),
        })

    print(f"\nMemory usage across all grids: {total_mem_mb:.1f} MB")
    print(f"Average per grid            : {total_mem_mb / len(grids):.1f} MB")

    # Save summary.
    summary_df = pd.DataFrame(summary_rows)
    summary_path = RESULTS_DIR / "second_grid_summary.csv"
    summary_df.to_csv(summary_path, index=False)
    print(f"\nSaved grid summary to: {summary_path}")
    print("Done.")
