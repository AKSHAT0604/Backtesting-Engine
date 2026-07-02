"""
Step 1.1 — Dataset Inventory

Maps the directory structure under Data/allData/, verifying the presence of
required futures files and counting option files by underlier prefix, without
reading any CSV row contents.

Outputs:
  - Printed summary to stdout.
  - dataset_inventory.csv saved to the results/ directory.

Usage:
  python step_1_1_dataset_inventory.py
"""

import os
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
from data_paths import resolve_data_root
DATA_ROOT = resolve_data_root(SCRIPT_DIR)
RESULTS_DIR = SCRIPT_DIR / "results"
OUTPUT_CSV = RESULTS_DIR / "dataset_inventory.csv"

FOLDER_PATTERN = re.compile(r"^NSE_(\d{8})$")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_trade_date(folder_name: str) -> str | None:
    """NSE_YYYYMMDD -> YYYY-MM-DD, or None if the folder name doesn't match."""
    m = FOLDER_PATTERN.match(folder_name)
    if not m:
        return None
    raw = m.group(1)
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"


def classify_option_filename(name: str) -> str:
    """
    Return 'NIFTY', 'BANKNIFTY', or 'OTHER' based on the filename prefix.
    FINNIFTY and MIDCPNIFTY (and anything else) fall into 'OTHER'.
    """
    # Check BANKNIFTY first — its prefix is longer and overlaps with NIFTY.
    if name.startswith("BANKNIFTY"):
        return "BANKNIFTY"
    if name.startswith("NIFTY"):
        return "NIFTY"
    return "OTHER"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not DATA_ROOT.is_dir():
        print(f"ERROR: Data root not found at {DATA_ROOT}")
        return

    # ---- 1. Discover dated folders ----------------------------------------
    all_entries = sorted(os.listdir(DATA_ROOT))
    dated_folders: list[tuple[str, str]] = []  # (folder_name, trade_date)

    for entry in all_entries:
        trade_date = parse_trade_date(entry)
        if trade_date is not None and (DATA_ROOT / entry).is_dir():
            dated_folders.append((entry, trade_date))

    print("=" * 70)
    print("STEP 1.1 — DATASET INVENTORY")
    print("=" * 70)
    print(f"\nData root: {DATA_ROOT}")
    print(f"Total trading days found: {len(dated_folders)}\n")

    print("Trading days:")
    for _, td in dated_folders:
        print(f"  {td}")
    print()

    # ---- 2 & 3. Check futures and count options per day -------------------
    rows: list[dict] = []
    warnings: list[str] = []

    for folder_name, trade_date in dated_folders:
        day_path = DATA_ROOT / folder_name
        futures_path = day_path / "Futures (Continuous)"
        options_path = day_path / "Options"

        # Futures presence check
        nifty_fut = (futures_path / "NIFTY-I.csv").is_file()
        banknifty_fut = (futures_path / "BANKNIFTY-I.csv").is_file()

        if not nifty_fut:
            warnings.append(f"WARNING: {trade_date} — NIFTY-I.csv MISSING in {futures_path}")
        if not banknifty_fut:
            warnings.append(f"WARNING: {trade_date} — BANKNIFTY-I.csv MISSING in {futures_path}")

        # Option file counts by prefix
        nifty_opts = 0
        banknifty_opts = 0
        other_opts = 0

        if options_path.is_dir():
            for fname in os.listdir(options_path):
                if not fname.endswith(".csv"):
                    continue
                category = classify_option_filename(fname)
                if category == "NIFTY":
                    nifty_opts += 1
                elif category == "BANKNIFTY":
                    banknifty_opts += 1
                else:
                    other_opts += 1

        rows.append({
            "trade_date": trade_date,
            "nifty_futures_present": nifty_fut,
            "banknifty_futures_present": banknifty_fut,
            "nifty_option_file_count": nifty_opts,
            "banknifty_option_file_count": banknifty_opts,
            "other_option_file_count": other_opts,
        })

    # Print warnings
    if warnings:
        print("WARNINGS:")
        for w in warnings:
            print(f"  {w}")
        print()
    else:
        print("No missing futures files detected.\n")

    # ---- 4. Save CSV ------------------------------------------------------
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Write CSV manually to avoid pandas dependency for this simple step.
    header = [
        "trade_date",
        "nifty_futures_present",
        "banknifty_futures_present",
        "nifty_option_file_count",
        "banknifty_option_file_count",
        "other_option_file_count",
    ]

    with open(OUTPUT_CSV, "w", newline="") as f:
        f.write(",".join(header) + "\n")
        for row in rows:
            line = ",".join(str(row[col]) for col in header)
            f.write(line + "\n")

    print(f"Inventory saved to: {OUTPUT_CSV}\n")

    # ---- 5. Summary -------------------------------------------------------
    total_days = len(rows)
    both_present = sum(
        1 for r in rows if r["nifty_futures_present"] and r["banknifty_futures_present"]
    )
    missing_days = [
        r["trade_date"]
        for r in rows
        if not r["nifty_futures_present"] or not r["banknifty_futures_present"]
    ]

    nifty_counts = [r["nifty_option_file_count"] for r in rows]
    banknifty_counts = [r["banknifty_option_file_count"] for r in rows]

    def stats(counts: list[int]) -> tuple[int, int, float]:
        return min(counts), max(counts), sum(counts) / len(counts)

    n_min, n_max, n_avg = stats(nifty_counts)
    b_min, b_max, b_avg = stats(banknifty_counts)

    print("-" * 70)
    print("SUMMARY")
    print("-" * 70)
    print(f"Total trading days         : {total_days}")
    print(f"Days with both futures     : {both_present}")
    print(f"Days missing >=1 futures   : {len(missing_days)}")
    if missing_days:
        for d in missing_days:
            print(f"  - {d}")
    print()
    print(f"NIFTY option files per day : min={n_min}, max={n_max}, avg={n_avg:.1f}")
    print(f"BANKNIFTY option files/day : min={b_min}, max={b_max}, avg={b_avg:.1f}")
    print()

    # Print the full table to stdout as well
    print("-" * 70)
    print("FULL INVENTORY TABLE")
    print("-" * 70)
    print(
        f"{'trade_date':<12} {'NIFTY-I':>8} {'BN-I':>8} "
        f"{'N_opts':>8} {'BN_opts':>8} {'Other':>8}"
    )
    print("-" * 70)
    for r in rows:
        print(
            f"{r['trade_date']:<12} "
            f"{'Yes' if r['nifty_futures_present'] else 'No':>8} "
            f"{'Yes' if r['banknifty_futures_present'] else 'No':>8} "
            f"{r['nifty_option_file_count']:>8} "
            f"{r['banknifty_option_file_count']:>8} "
            f"{r['other_option_file_count']:>8}"
        )
    print("-" * 70)
    print("Done.")


if __name__ == "__main__":
    main()
