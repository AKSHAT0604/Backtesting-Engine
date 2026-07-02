"""
Step 1.2 — Dataset Understanding (Option Filename Parsing)

Applies the pure option filename parser to every option file in the dataset,
builds a master metadata table, and saves it to option_metadata.csv.

Outputs:
  - Printed test results and summary to stdout.
  - option_metadata.csv saved to the results/ directory.

Usage:
  python step_1_2_parse_filenames.py
"""

import os
import re
import sys
from pathlib import Path
from collections import Counter

# Engine modules live in ../engine — put it on the path before importing them.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from option_filename_parser import parse_option_filename
from data_paths import resolve_data_root, results_dir

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_ROOT = resolve_data_root()
RESULTS_DIR = results_dir()
OUTPUT_CSV = RESULTS_DIR / "option_metadata.csv"

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

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run_inline_tests():
    print("=" * 70)
    print("INLINE TESTS")
    print("=" * 70)
    
    test_cases = [
        (
            "NIFTY22110314550PE.csv",
            {"underlier": "NIFTY", "expiry_date": "2022-11-03", "strike": 14550, "option_type": "PE", "parse_status": "OK"}
        ),
        (
            "BANKNIFTY22112443200CE.csv",
            {"underlier": "BANKNIFTY", "expiry_date": "2022-11-24", "strike": 43200, "option_type": "CE", "parse_status": "OK"}
        ),
        (
            "FINNIFTY22110719500CE.csv",
            {"underlier": "FINNIFTY", "expiry_date": "2022-11-07", "strike": 19500, "option_type": "CE", "parse_status": "OK"}
        )
    ]
    
    all_passed = True
    for filename, expected in test_cases:
        result = parse_option_filename(filename)
        passed = True
        for k, v in expected.items():
            if result.get(k) != v:
                passed = False
                print(f"FAIL: {filename} -> Expected {k}={v}, got {result.get(k)}")
                
        if passed:
            print(f"PASS: {filename}")
        else:
            all_passed = False
            
    print()
    return all_passed

def main():
    if not run_inline_tests():
        print("Tests failed. Aborting.")
        return

    print("=" * 70)
    print("STEP 1.2 — PARSING OPTION FILENAMES")
    print("=" * 70)

    if not DATA_ROOT.is_dir():
        print(f"ERROR: Data root not found at {DATA_ROOT}")
        return

    # ---- 1. Discover dated folders and process option files ---------------
    all_entries = sorted(os.listdir(DATA_ROOT))
    dated_folders: list[tuple[str, str]] = []  # (folder_name, trade_date)

    for entry in all_entries:
        trade_date = parse_trade_date(entry)
        if trade_date is not None and (DATA_ROOT / entry).is_dir():
            dated_folders.append((entry, trade_date))

    rows = []
    
    total_files = 0
    total_parsed = 0
    total_failed = 0
    
    underlier_counts = Counter()
    failure_reasons = Counter()

    for folder_name, trade_date in dated_folders:
        options_path = DATA_ROOT / folder_name / "Options"
        if not options_path.is_dir():
            continue
            
        for fname in os.listdir(options_path):
            if not fname.endswith(".csv"):
                continue
                
            total_files += 1
            result = parse_option_filename(fname)
            
            # Combine trade_date with parsed data
            row = {"trade_date": trade_date}
            row.update(result)
            rows.append(row)
            
            if result["parse_status"] == "OK":
                total_parsed += 1
                underlier_counts[result["underlier"]] += 1
            else:
                total_failed += 1
                failure_reasons[result["failure_reason"]] += 1
                underlier_counts["unknown"] += 1

    # ---- 2. Save CSV ------------------------------------------------------
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    
    header = [
        "trade_date",
        "filename",
        "underlier",
        "expiry_date",
        "strike",
        "option_type",
        "instrument_name",
        "parse_status",
        "failure_reason"
    ]

    with open(OUTPUT_CSV, "w", newline="") as f:
        f.write(",".join(header) + "\n")
        for row in rows:
            line = ",".join(str(row.get(col, "")) for col in header)
            f.write(line + "\n")

    print(f"Saved master metadata table to: {OUTPUT_CSV}\n")

    # ---- 3. Summary -------------------------------------------------------
    print("-" * 70)
    print("SUMMARY")
    print("-" * 70)
    print(f"Total option files scanned : {total_files}")
    print(f"Total parsed successfully  : {total_parsed}")
    print(f"Total failed to parse      : {total_failed}")
    
    if total_failed > 0:
        print("\nFailure Reasons:")
        for reason, count in failure_reasons.items():
            print(f"  - {count:4d} files: {reason}")
            
    print("\nUnderlier Breakdown:")
    for underlier in ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "unknown"]:
        count = underlier_counts.get(underlier, 0)
        print(f"  {underlier:<12}: {count}")
    
    print("-" * 70)
    print("Done.")

if __name__ == "__main__":
    main()
