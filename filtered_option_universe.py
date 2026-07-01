"""
filtered_option_universe.py — Builds the filtered option universe for each day.

Exports:
    build_filtered_option_universe(option_metadata_df, nearest_expiry_df) -> pd.DataFrame
    get_eligible_strikes(filtered_universe_df, trade_date, underlier) -> pd.DataFrame

Governed by:
    SPEC.md Rule 3  — only NIFTY and BANKNIFTY
    SPEC.md Rule 5  — only nearest-expiry contracts
    ASSUMPTIONS.md A7 — strike eligible only if both CE and PE files exist
"""

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

_TRADABLE_UNDERLIERS = {"NIFTY", "BANKNIFTY"}


def build_filtered_option_universe(
    option_metadata_df: pd.DataFrame,
    nearest_expiry_df: pd.DataFrame,
) -> pd.DataFrame:
    """Join metadata with nearest-expiry lookup and return only tradable rows.

    Parameters
    ----------
    option_metadata_df : pd.DataFrame
        Master metadata table from Step 1.2.
    nearest_expiry_df : pd.DataFrame
        Nearest-expiry lookup from Step 2.2 (trade_date, underlier, selected_expiry).

    Returns
    -------
    pd.DataFrame
        Columns: trade_date, underlier, expiry_date, strike, option_type,
                 instrument_name, filename.
        Contains only rows where:
          - underlier is NIFTY or BANKNIFTY
          - parse_status == "OK"
          - expiry_date == selected_expiry for that (trade_date, underlier)
    """
    meta = option_metadata_df.copy()

    # ---- Filter to tradable underliers and successfully parsed rows -------
    meta = meta[
        (meta["underlier"].isin(_TRADABLE_UNDERLIERS))
        & (meta["parse_status"] == "OK")
    ].copy()

    # ---- Join with nearest expiry to get selected_expiry per row ----------
    merged = meta.merge(
        nearest_expiry_df[["trade_date", "underlier", "selected_expiry"]],
        on=["trade_date", "underlier"],
        how="inner",
    )

    # ---- Keep only rows whose expiry matches the selected nearest expiry --
    filtered = merged[merged["expiry_date"] == merged["selected_expiry"]].copy()

    # ---- Ensure strike is numeric -----------------------------------------
    filtered["strike"] = pd.to_numeric(filtered["strike"], errors="coerce")
    bad_strikes = filtered["strike"].isna().sum()
    if bad_strikes:
        logger.warning("%d rows dropped due to non-numeric strike after filtering.", bad_strikes)
        filtered = filtered[filtered["strike"].notna()].copy()

    # ---- Select output columns and sort -----------------------------------
    out_cols = [
        "trade_date", "underlier", "expiry_date", "strike",
        "option_type", "instrument_name", "filename",
    ]
    result = filtered[out_cols].sort_values(
        ["trade_date", "underlier", "strike", "option_type"]
    ).reset_index(drop=True)

    logger.info(
        "Filtered option universe: %d rows (from %d raw metadata rows).",
        len(result), len(option_metadata_df),
    )
    return result


def get_eligible_strikes(
    filtered_universe_df: pd.DataFrame,
    trade_date: str,
    underlier: str,
) -> pd.DataFrame:
    """Return strikes where both CE and PE files exist for a given day/underlier.

    Parameters
    ----------
    filtered_universe_df : pd.DataFrame
        Output of build_filtered_option_universe.
    trade_date : str
        Trading day in YYYY-MM-DD format.
    underlier : str
        "NIFTY" or "BANKNIFTY".

    Returns
    -------
    pd.DataFrame
        Columns: strike, ce_filename, ce_instrument_name, pe_filename, pe_instrument_name.
        Only strikes with both legs present are included, sorted by strike ascending.
    """
    day = filtered_universe_df[
        (filtered_universe_df["trade_date"] == trade_date)
        & (filtered_universe_df["underlier"] == underlier)
    ].copy()

    if day.empty:
        logger.warning("[%s] %s: no option data in filtered universe.", trade_date, underlier)
        return pd.DataFrame(columns=[
            "strike", "ce_filename", "ce_instrument_name",
            "pe_filename", "pe_instrument_name",
        ])

    # Pivot CE and PE into separate columns per strike.
    ce = day[day["option_type"] == "CE"][["strike", "filename", "instrument_name"]].copy()
    ce.columns = ["strike", "ce_filename", "ce_instrument_name"]

    pe = day[day["option_type"] == "PE"][["strike", "filename", "instrument_name"]].copy()
    pe.columns = ["strike", "pe_filename", "pe_instrument_name"]

    # Inner join on strike — only strikes with BOTH legs survive.
    both = ce.merge(pe, on="strike", how="inner")

    result = both.sort_values("strike").reset_index(drop=True)

    # Log dropped single-leg strikes.
    all_strikes = set(day["strike"].unique())
    eligible_strikes = set(result["strike"].unique())
    dropped = all_strikes - eligible_strikes
    if dropped:
        logger.info(
            "[%s] %s: %d single-leg strike(s) dropped: %s",
            trade_date, underlier, len(dropped), sorted(dropped),
        )

    return result


# ---------------------------------------------------------------------------
# Standalone runner — produces results/filtered_option_universe.csv
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(message)s",
        stream=sys.stdout,
    )

    SCRIPT_DIR = Path(__file__).resolve().parent
    RESULTS_DIR = SCRIPT_DIR / "results"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    METADATA_CSV = RESULTS_DIR / "option_metadata.csv"
    EXPIRY_CSV = RESULTS_DIR / "nearest_expiry.csv"
    OUTPUT_CSV = RESULTS_DIR / "filtered_option_universe.csv"

    print("=" * 70)
    print("STEP 2.3 — FILTERED OPTION UNIVERSE")
    print("=" * 70)

    # ---- Load inputs ------------------------------------------------------
    meta = pd.read_csv(METADATA_CSV, dtype=str)
    expiry = pd.read_csv(EXPIRY_CSV, dtype=str)
    print(f"Loaded option_metadata.csv    : {len(meta)} rows")
    print(f"Loaded nearest_expiry.csv     : {len(expiry)} rows\n")

    # ---- Build filtered universe ------------------------------------------
    universe = build_filtered_option_universe(meta, expiry)
    universe.to_csv(OUTPUT_CSV, index=False)
    print(f"Saved filtered universe to    : {OUTPUT_CSV}")
    print(f"Filtered universe row count   : {len(universe)}")
    print(f"Raw metadata row count        : {len(meta)}")
    print(f"Reduction                     : {len(meta) - len(universe)} rows removed "
          f"({100 * (1 - len(universe) / len(meta)):.1f}%)\n")

    # ---- Per (trade_date, underlier) summary ------------------------------
    summary = (
        universe
        .groupby(["trade_date", "underlier"])
        .agg(
            total_files=("filename", "count"),
            unique_strikes=("strike", "nunique"),
            ce_count=("option_type", lambda x: (x == "CE").sum()),
            pe_count=("option_type", lambda x: (x == "PE").sum()),
        )
        .reset_index()
    )

    summary_path = RESULTS_DIR / "filtered_universe_summary.csv"
    summary.to_csv(summary_path, index=False)
    print(f"Saved per-day summary to      : {summary_path}\n")

    print(f"{'trade_date':<14} {'underlier':<12} {'files':>6} {'strikes':>8} {'CE':>5} {'PE':>5}")
    print("-" * 55)
    for _, row in summary.iterrows():
        print(
            f"{row['trade_date']:<14} {row['underlier']:<12} "
            f"{row['total_files']:>6} {row['unique_strikes']:>8} "
            f"{row['ce_count']:>5} {row['pe_count']:>5}"
        )

    # ---- Validation: eligible strikes for (2022-11-01, NIFTY) -------------
    print("\n" + "-" * 70)
    print("VALIDATION: Eligible strikes for (2022-11-01, NIFTY)")
    print("-" * 70)

    day_nifty = universe[
        (universe["trade_date"] == "2022-11-01") & (universe["underlier"] == "NIFTY")
    ]
    total_strikes_day = day_nifty["strike"].nunique()
    ce_strikes = set(day_nifty[day_nifty["option_type"] == "CE"]["strike"])
    pe_strikes = set(day_nifty[day_nifty["option_type"] == "PE"]["strike"])
    both_strikes = ce_strikes & pe_strikes
    ce_only = ce_strikes - pe_strikes
    pe_only = pe_strikes - ce_strikes

    print(f"Total unique strikes (CE or PE)      : {total_strikes_day}")
    print(f"Strikes with BOTH CE and PE (eligible): {len(both_strikes)}")
    print(f"CE-only strikes (will be dropped)     : {len(ce_only)}")
    print(f"PE-only strikes (will be dropped)     : {len(pe_only)}")

    if ce_only:
        print(f"  CE-only values: {sorted(ce_only)[:10]}{'...' if len(ce_only) > 10 else ''}")
    if pe_only:
        print(f"  PE-only values: {sorted(pe_only)[:10]}{'...' if len(pe_only) > 10 else ''}")

    # Also run get_eligible_strikes to confirm it matches.
    eligible = get_eligible_strikes(universe, "2022-11-01", "NIFTY")
    print(f"\nget_eligible_strikes() returned       : {len(eligible)} strikes")
    assert len(eligible) == len(both_strikes), (
        f"Mismatch: {len(eligible)} vs {len(both_strikes)}"
    )
    print("PASS: get_eligible_strikes matches manual count.")

    print(f"\nSample (first 5 eligible strikes):")
    print(eligible.head().to_string(index=False))

    print("\nDone.")
