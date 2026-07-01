"""
nearest_expiry_selector.py — Determines the nearest tradable expiry per day/underlier.

Exports:
    select_nearest_expiry(option_metadata_df) -> pd.DataFrame

Governed by SPEC.md Rule 5:
    "For each underlier on each trading day, the system SHALL determine the
    nearest expiry by parsing expiry dates from option filenames and selecting
    the earliest expiry date that is >= the current trading date."
"""

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Only these underliers are tradable (SPEC.md Rule 3).
_TRADABLE_UNDERLIERS = {"NIFTY", "BANKNIFTY"}


def select_nearest_expiry(option_metadata_df: pd.DataFrame) -> pd.DataFrame:
    """Select the nearest tradable expiry for each (trade_date, underlier).

    Parameters
    ----------
    option_metadata_df : pd.DataFrame
        The master metadata table with at least columns:
        trade_date, underlier, expiry_date, parse_status.

    Returns
    -------
    pd.DataFrame
        Columns: trade_date, underlier, selected_expiry.
        One row per (trade_date, underlier) pair.
        selected_expiry is None where no valid expiry exists.
    """
    df = option_metadata_df.copy()

    # ---- Filter to tradable underliers and successfully parsed rows -------
    df = df[
        (df["underlier"].isin(_TRADABLE_UNDERLIERS))
        & (df["parse_status"] == "OK")
    ].copy()

    # ---- Ensure date columns are comparable strings (YYYY-MM-DD) ----------
    # Both trade_date and expiry_date are already YYYY-MM-DD strings from the
    # parser, so lexicographic comparison works correctly.

    # ---- Keep only contracts whose expiry has NOT already passed -----------
    df = df[df["expiry_date"] >= df["trade_date"]].copy()

    # ---- For each (trade_date, underlier), find min expiry_date -----------
    if df.empty:
        logger.warning("No valid (trade_date, underlier, expiry_date) rows after filtering.")
        return pd.DataFrame(columns=["trade_date", "underlier", "selected_expiry"])

    nearest = (
        df.groupby(["trade_date", "underlier"], as_index=False)["expiry_date"]
        .min()
        .rename(columns={"expiry_date": "selected_expiry"})
    )

    # ---- Fill in missing (trade_date, underlier) pairs with null ----------
    # Build the full expected grid from the original metadata.
    all_trade_dates = sorted(option_metadata_df["trade_date"].unique())
    full_grid = pd.DataFrame(
        [
            (td, ul)
            for td in all_trade_dates
            for ul in sorted(_TRADABLE_UNDERLIERS)
        ],
        columns=["trade_date", "underlier"],
    )

    result = full_grid.merge(nearest, on=["trade_date", "underlier"], how="left")

    # Log warnings for any missing expiries.
    missing = result[result["selected_expiry"].isna()]
    for _, row in missing.iterrows():
        logger.warning(
            "[%s] %s: no valid expiry found (all contracts expired or no data).",
            row["trade_date"], row["underlier"],
        )

    # ---- Sanity: no more than one row per (trade_date, underlier) ---------
    dupes = result.duplicated(subset=["trade_date", "underlier"], keep=False)
    if dupes.any():
        raise AssertionError(
            f"Duplicate (trade_date, underlier) rows detected:\n"
            f"{result[dupes]}"
        )

    return result[["trade_date", "underlier", "selected_expiry"]].reset_index(drop=True)


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

    SCRIPT_DIR = Path(__file__).resolve().parent
    METADATA_CSV = SCRIPT_DIR / "results" / "option_metadata.csv"
    OUTPUT_CSV = SCRIPT_DIR / "results" / "nearest_expiry.csv"

    print("=" * 70)
    print("STEP 2.2 — NEAREST EXPIRY SELECTION")
    print("=" * 70)

    # ---- Load metadata ----------------------------------------------------
    meta = pd.read_csv(METADATA_CSV, dtype=str)
    print(f"Loaded {len(meta)} rows from option_metadata.csv.\n")

    # ---- Run selector -----------------------------------------------------
    expiry_df = select_nearest_expiry(meta)

    # ---- Save output ------------------------------------------------------
    expiry_df.to_csv(OUTPUT_CSV, index=False)
    print(f"Saved {len(expiry_df)} rows to {OUTPUT_CSV}.\n")

    # ---- Print full table -------------------------------------------------
    print(f"{'trade_date':<14} {'underlier':<12} {'selected_expiry'}")
    print("-" * 42)
    for _, row in expiry_df.iterrows():
        print(f"{row['trade_date']:<14} {row['underlier']:<12} {row['selected_expiry']}")
    print()

    # ---- Validation: sample case from assignment brief --------------------
    print("-" * 70)
    print("VALIDATION CHECKS")
    print("-" * 70)

    # Check 1: NIFTY on 2022-11-01 should select expiry 2022-11-03.
    check_row = expiry_df[
        (expiry_df["trade_date"] == "2022-11-01")
        & (expiry_df["underlier"] == "NIFTY")
    ]
    if check_row.empty:
        print("FAIL: No row found for (2022-11-01, NIFTY).")
    else:
        actual = check_row.iloc[0]["selected_expiry"]
        expected = "2022-11-03"
        status = "PASS" if actual == expected else "FAIL"
        print(f"{status}: (2022-11-01, NIFTY) -> selected_expiry={actual}  (expected {expected})")

    # Check 2: No duplicate (trade_date, underlier) pairs.
    n_pairs = len(expiry_df)
    n_unique = len(expiry_df.drop_duplicates(subset=["trade_date", "underlier"]))
    status2 = "PASS" if n_pairs == n_unique else "FAIL"
    print(f"{status2}: Uniqueness check — {n_pairs} rows, {n_unique} unique pairs.")

    # Check 3: No null selected_expiry values.
    n_null = expiry_df["selected_expiry"].isna().sum()
    status3 = "PASS" if n_null == 0 else f"WARN ({n_null} nulls)"
    print(f"{status3}: Null check — {n_null} rows with null selected_expiry.")

    print("\nDone.")
