"""
futures_loader.py — Futures data loader for Phase 2.

Exports:
    load_futures_file(filepath, trade_date, underlier) -> pd.DataFrame
    load_all_futures(base_path, trade_dates) -> dict[(trade_date, underlier), pd.DataFrame]

Behaviour is governed by ASSUMPTIONS.md:
  A2  — last tick in same second wins (keep='last' in drop_duplicates)
  A3  — forward-fill handled downstream in the market-data layer
  A4  — no price before first tick is handled downstream
  A10 — no cost adjustments applied here
"""

import logging
import re
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Module-level logger
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Only the nearest continuous contract is used (SPEC.md Rule 4).
UNDERLIERS = ("NIFTY", "BANKNIFTY")

# Raw CSV columns — headerless file.
_RAW_COLS = ["_date_str", "_time_str", "price", "volume", "open_interest"]

# Final public column order.
OUTPUT_COLS = ["trade_date", "underlier", "timestamp", "price", "volume", "open_interest"]

# Folder pattern for dated subfolders.
_FOLDER_RE = re.compile(r"^NSE_(\d{8})$")


# ---------------------------------------------------------------------------
# Core loader
# ---------------------------------------------------------------------------

def load_futures_file(
    filepath: str | Path,
    trade_date: str,
    underlier: str,
) -> pd.DataFrame:
    """Load a single headerless futures CSV and return a clean DataFrame.

    Parameters
    ----------
    filepath : str | Path
        Absolute path to the CSV file (e.g. path to NIFTY-I.csv).
    trade_date : str
        The trading day in ``YYYY-MM-DD`` format, attached as a column.
    underlier : str
        One of ``"NIFTY"`` or ``"BANKNIFTY"``, attached as a column.

    Returns
    -------
    pd.DataFrame
        Columns: trade_date, underlier, timestamp, price, volume, open_interest.
        Sorted by timestamp (stable). One row per second (last tick wins).
        Empty DataFrame with the correct columns if the file is unreadable or empty.
    """
    filepath = Path(filepath)
    empty_result = pd.DataFrame(columns=OUTPUT_COLS)

    # ---- 1. Read raw CSV --------------------------------------------------
    try:
        raw = pd.read_csv(
            filepath,
            header=None,
            names=_RAW_COLS,
            dtype={"_date_str": str, "_time_str": str},
            engine="c",
        )
    except Exception as exc:
        logger.warning("[%s] Failed to read %s: %s", trade_date, filepath.name, exc)
        return empty_result

    initial_rows = len(raw)
    if initial_rows == 0:
        logger.warning("[%s] %s is empty (0 rows).", trade_date, filepath.name)
        return empty_result

    logger.debug("[%s] %s: read %d raw rows.", trade_date, filepath.name, initial_rows)

    # ---- 2. Parse timestamp -----------------------------------------------
    # Date column is YYYYMMDD (integer or string).
    # Time column is HH:MM:SS.
    raw["_date_str"] = raw["_date_str"].astype(str).str.strip()
    raw["_time_str"] = raw["_time_str"].astype(str).str.strip()

    raw["timestamp"] = pd.to_datetime(
        raw["_date_str"] + " " + raw["_time_str"],
        format="%Y%m%d %H:%M:%S",
        errors="coerce",
    )

    bad_ts = raw["timestamp"].isna().sum()
    if bad_ts:
        logger.warning(
            "[%s] %s: %d row(s) had unparseable timestamps and will be dropped.",
            trade_date, filepath.name, bad_ts,
        )
        raw = raw[raw["timestamp"].notna()].copy()

    # ---- 3. Coerce numeric columns ----------------------------------------
    for col in ("price", "volume", "open_interest"):
        raw[col] = pd.to_numeric(raw[col], errors="coerce")

    bad_price = raw["price"].isna().sum()
    if bad_price:
        logger.warning(
            "[%s] %s: %d row(s) dropped due to non-numeric price.",
            trade_date, filepath.name, bad_price,
        )
    raw = raw[raw["price"].notna()].copy()

    if raw.empty:
        logger.warning("[%s] %s: no valid rows remaining after cleaning.", trade_date, filepath.name)
        return empty_result

    # ---- 4. Sort by timestamp (stable) ------------------------------------
    raw.sort_values("timestamp", kind="stable", inplace=True)

    # ---- 5. Drop duplicate timestamps — keep last (A2) --------------------
    before_dedup = len(raw)
    raw.drop_duplicates(subset=["timestamp"], keep="last", inplace=True)
    deduped = before_dedup - len(raw)
    if deduped:
        logger.debug(
            "[%s] %s: %d duplicate-second row(s) collapsed (last tick kept).",
            trade_date, filepath.name, deduped,
        )

    # ---- 6. Attach metadata columns and select output ---------------------
    raw["trade_date"] = trade_date
    raw["underlier"] = underlier

    result = raw[OUTPUT_COLS].reset_index(drop=True)

    logger.info(
        "[%s] %s loaded: %d raw -> %d final rows (%d bad-ts, %d bad-price, %d deduped).",
        trade_date, filepath.name,
        initial_rows, len(result),
        bad_ts, bad_price, deduped,
    )

    return result


# ---------------------------------------------------------------------------
# Batch loader
# ---------------------------------------------------------------------------

def load_all_futures(
    base_path: str | Path,
    trade_dates: list[str],
) -> dict[tuple[str, str], pd.DataFrame]:
    """Load NIFTY-I.csv and BANKNIFTY-I.csv for every trading day.

    Parameters
    ----------
    base_path : str | Path
        Root of the dataset, i.e. the ``Data/allData/`` directory.
    trade_dates : list[str]
        Ordered list of trading dates in ``YYYY-MM-DD`` format.
        Each must correspond to a ``NSE_YYYYMMDD`` subfolder.

    Returns
    -------
    dict
        Keys are ``(trade_date, underlier)`` tuples.
        Values are the standardised DataFrames returned by ``load_futures_file``.
        A missing or unreadable file produces an empty DataFrame value (logged
        as a warning) rather than raising.
    """
    base_path = Path(base_path)
    futures_store: dict[tuple[str, str], pd.DataFrame] = {}

    for trade_date in trade_dates:
        # Reconstruct folder name from trade_date (YYYY-MM-DD -> NSE_YYYYMMDD).
        folder_name = "NSE_" + trade_date.replace("-", "")
        futures_dir = base_path / folder_name / "Futures (Continuous)"

        if not futures_dir.is_dir():
            logger.warning(
                "[%s] Futures (Continuous) folder not found at %s",
                trade_date, futures_dir,
            )
            for underlier in UNDERLIERS:
                futures_store[(trade_date, underlier)] = pd.DataFrame(columns=OUTPUT_COLS)
            continue

        for underlier in UNDERLIERS:
            csv_name = f"{underlier}-I.csv"
            filepath = futures_dir / csv_name

            if not filepath.is_file():
                logger.warning(
                    "[%s] %s not found — storing empty DataFrame.",
                    trade_date, csv_name,
                )
                futures_store[(trade_date, underlier)] = pd.DataFrame(columns=OUTPUT_COLS)
                continue

            df = load_futures_file(filepath, trade_date, underlier)
            futures_store[(trade_date, underlier)] = df

    total_keys = len(futures_store)
    non_empty = sum(1 for df in futures_store.values() if not df.empty)
    logger.info(
        "load_all_futures complete: %d / %d (date, underlier) pairs loaded non-empty.",
        non_empty, total_keys,
    )

    return futures_store


# ---------------------------------------------------------------------------
# Standalone runner — produces results/futures_summary.csv
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(message)s",
        stream=sys.stdout,
    )

    _script_dir = Path(__file__).resolve().parent
    _data_root = _script_dir / "Data" / "allData"
    _results_dir = _script_dir / "results"
    _results_dir.mkdir(parents=True, exist_ok=True)

    # Discover trade dates from folder names.
    _trade_dates = []
    for _d in sorted(_data_root.iterdir()):
        _m = _FOLDER_RE.match(_d.name)
        if _m and _d.is_dir():
            _raw = _m.group(1)
            _trade_dates.append(f"{_raw[:4]}-{_raw[4:6]}-{_raw[6:8]}")

    print(f"Found {len(_trade_dates)} trading days.\n")

    _store = load_all_futures(_data_root, _trade_dates)

    # ---- Print summary table to stdout ------------------------------------
    print(f"\n{'(trade_date, underlier)':<35} {'rows':>6}  {'first_ts':<22}  {'last_ts'}")
    print("-" * 80)
    for _key in sorted(_store.keys()):
        _df = _store[_key]
        if _df.empty:
            print(f"{str(_key):<35} {'EMPTY':>6}")
        else:
            print(
                f"{str(_key):<35} {len(_df):>6}  "
                f"{str(_df['timestamp'].iloc[0]):<22}  "
                f"{str(_df['timestamp'].iloc[-1])}"
            )

    # ---- Save results/futures_summary.csv ---------------------------------
    _summary_rows = []
    for _key in sorted(_store.keys()):
        _df = _store[_key]
        _summary_rows.append({
            "trade_date": _key[0],
            "underlier": _key[1],
            "row_count": len(_df),
            "first_timestamp": str(_df["timestamp"].iloc[0]) if not _df.empty else "",
            "last_timestamp": str(_df["timestamp"].iloc[-1]) if not _df.empty else "",
            "first_price": float(_df["price"].iloc[0]) if not _df.empty else "",
            "last_price": float(_df["price"].iloc[-1]) if not _df.empty else "",
        })

    _summary_path = _results_dir / "futures_summary.csv"
    _summary_df = pd.DataFrame(_summary_rows)
    _summary_df.to_csv(_summary_path, index=False)
    print(f"\nSaved futures summary to: {_summary_path}")
    print("Done.")

