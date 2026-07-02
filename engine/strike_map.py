"""
strike_map.py — Phase 3, Step 3.1: Available strike map builder.

Exports:
    build_strike_map(filtered_universe_df) -> dict[(trade_date, underlier), pd.DataFrame]
    get_eligible_strikes(strike_map_dict, trade_date, underlier)
        -> (list[int|float], dict[strike, (ce_instr, pe_instr)])

Governed by:
    SPEC.md Rule 3  — only NIFTY and BANKNIFTY
    SPEC.md Rule 5  — only nearest-expiry contracts (already filtered upstream)
    ASSUMPTIONS.md A7 — strike eligible only if both CE and PE files exist
"""

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def build_strike_map(
    filtered_universe_df: pd.DataFrame,
) -> dict[tuple[str, str], pd.DataFrame]:
    """Build a per-(trade_date, underlier) strike availability map.

    Parameters
    ----------
    filtered_universe_df : pd.DataFrame
        Output of ``build_filtered_option_universe`` from Step 2.3.
        Required columns: trade_date, underlier, strike, option_type,
        instrument_name.

    Returns
    -------
    dict[(trade_date, underlier), pd.DataFrame]
        Each DataFrame has columns:
            strike              — the strike price (numeric)
            has_ce              — bool, True if a CE file exists
            has_pe              — bool, True if a PE file exists
            ce_instrument_name  — str or None
            pe_instrument_name  — str or None
        Sorted by strike ascending.
    """
    df = filtered_universe_df.copy()
    df["strike"] = pd.to_numeric(df["strike"], errors="coerce")

    result: dict[tuple[str, str], pd.DataFrame] = {}

    for (trade_date, underlier), group in df.groupby(["trade_date", "underlier"]):
        ce = group[group["option_type"] == "CE"][["strike", "instrument_name"]].copy()
        ce.columns = ["strike", "ce_instrument_name"]
        ce = ce.drop_duplicates(subset=["strike"], keep="last")

        pe = group[group["option_type"] == "PE"][["strike", "instrument_name"]].copy()
        pe.columns = ["strike", "pe_instrument_name"]
        pe = pe.drop_duplicates(subset=["strike"], keep="last")

        # Full outer join on strike — keeps strikes with only one leg too.
        merged = ce.merge(pe, on="strike", how="outer")

        merged["has_ce"] = merged["ce_instrument_name"].notna()
        merged["has_pe"] = merged["pe_instrument_name"].notna()

        merged.sort_values("strike", inplace=True)
        merged.reset_index(drop=True, inplace=True)

        out_cols = [
            "strike", "has_ce", "has_pe",
            "ce_instrument_name", "pe_instrument_name",
        ]
        result[(trade_date, underlier)] = merged[out_cols]

    logger.info(
        "build_strike_map complete: %d (trade_date, underlier) entries.", len(result),
    )
    return result


def get_eligible_strikes(
    strike_map_dict: dict[tuple[str, str], pd.DataFrame],
    trade_date: str,
    underlier: str,
) -> tuple[list[int | float], dict[int | float, tuple[str, str]]]:
    """Return only strikes where both CE and PE exist.

    Parameters
    ----------
    strike_map_dict : dict
        Output of ``build_strike_map``.
    trade_date : str
        Trading day in YYYY-MM-DD format.
    underlier : str
        "NIFTY" or "BANKNIFTY".

    Returns
    -------
    eligible_strikes : list[int|float]
        Sorted ascending list of strikes with both legs.
    instrument_lookup : dict[strike, (ce_instrument_name, pe_instrument_name)]
        Quick lookup for downstream modules.
    """
    key = (trade_date, underlier)
    if key not in strike_map_dict:
        logger.warning("[%s] %s: not found in strike map.", trade_date, underlier)
        return [], {}

    smap = strike_map_dict[key]
    both = smap[smap["has_ce"] & smap["has_pe"]].copy()

    eligible_strikes = sorted(both["strike"].tolist())

    instrument_lookup = {
        row["strike"]: (row["ce_instrument_name"], row["pe_instrument_name"])
        for _, row in both.iterrows()
    }

    return eligible_strikes, instrument_lookup


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

    from filtered_option_universe import build_filtered_option_universe

    SCRIPT_DIR = Path(__file__).resolve().parent
    RESULTS_DIR = SCRIPT_DIR / "results"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("STEP 3.1 — AVAILABLE STRIKE MAP")
    print("=" * 70)

    # ---- Load filtered universe -------------------------------------------
    meta = pd.read_csv(RESULTS_DIR / "option_metadata.csv", dtype=str)
    expiry = pd.read_csv(RESULTS_DIR / "nearest_expiry.csv", dtype=str)
    universe = build_filtered_option_universe(meta, expiry)
    print(f"Filtered universe loaded: {len(universe)} rows.\n")

    # ---- Build strike map -------------------------------------------------
    smap = build_strike_map(universe)
    print(f"Strike map built for {len(smap)} (trade_date, underlier) pairs.\n")

    # ---- Save CSV output: one row per (trade_date, underlier, strike) -----
    all_rows = []
    for (td, ul), df in sorted(smap.items()):
        df_out = df.copy()
        df_out.insert(0, "trade_date", td)
        df_out.insert(1, "underlier", ul)
        all_rows.append(df_out)

    strike_map_csv = pd.concat(all_rows, ignore_index=True)
    output_path = RESULTS_DIR / "strike_map.csv"
    strike_map_csv.to_csv(output_path, index=False)
    print(f"Saved strike map to: {output_path}")
    print(f"Total rows: {len(strike_map_csv)}\n")

    # ---- Per-day summary --------------------------------------------------
    summary_rows = []
    for (td, ul), df in sorted(smap.items()):
        total = len(df)
        eligible = int((df["has_ce"] & df["has_pe"]).sum())
        ce_only = int(df["has_ce"].sum() - eligible)
        pe_only = int(df["has_pe"].sum() - eligible)
        min_s = df["strike"].min()
        max_s = df["strike"].max()
        elig_df = df[df["has_ce"] & df["has_pe"]]
        min_e = elig_df["strike"].min() if not elig_df.empty else None
        max_e = elig_df["strike"].max() if not elig_df.empty else None
        summary_rows.append({
            "trade_date": td,
            "underlier": ul,
            "total_strikes": total,
            "eligible_strikes": eligible,
            "ce_only": ce_only,
            "pe_only": pe_only,
            "min_eligible_strike": min_e,
            "max_eligible_strike": max_e,
        })

    summary_df = pd.DataFrame(summary_rows)
    summary_path = RESULTS_DIR / "strike_map_summary.csv"
    summary_df.to_csv(summary_path, index=False)
    print(f"Saved summary to: {summary_path}\n")

    print(f"{'trade_date':<14} {'underlier':<12} {'total':>6} {'eligible':>9} "
          f"{'CE-only':>8} {'PE-only':>8} {'min_elig':>10} {'max_elig':>10}")
    print("-" * 82)
    for _, r in summary_df.iterrows():
        print(
            f"{r['trade_date']:<14} {r['underlier']:<12} "
            f"{r['total_strikes']:>6} {r['eligible_strikes']:>9} "
            f"{r['ce_only']:>8} {r['pe_only']:>8} "
            f"{r['min_eligible_strike']:>10} {r['max_eligible_strike']:>10}"
        )

    # ---- Validation: (2022-11-01, NIFTY) ----------------------------------
    print("\n" + "-" * 70)
    print("VALIDATION: (2022-11-01, NIFTY)")
    print("-" * 70)

    eligible_strikes, instr_lookup = get_eligible_strikes(smap, "2022-11-01", "NIFTY")
    val_smap = smap[("2022-11-01", "NIFTY")]
    total_strikes = len(val_smap)
    n_eligible = len(eligible_strikes)

    print(f"Total unique strikes found    : {total_strikes}")
    print(f"Eligible (both CE + PE)       : {n_eligible}")
    print(f"CE-only (dropped)             : {int(val_smap['has_ce'].sum()) - n_eligible}")
    print(f"PE-only (dropped)             : {int(val_smap['has_pe'].sum()) - n_eligible}")
    print(f"Min eligible strike           : {min(eligible_strikes)}")
    print(f"Max eligible strike           : {max(eligible_strikes)}")
    print(f"\nNIFTY spot was ~18,100-18,200 on 2022-11-01.")
    print(f"Strike range [{min(eligible_strikes)} .. {max(eligible_strikes)}] "
          f"looks {'reasonable' if 15000 <= min(eligible_strikes) <= 18200 <= max(eligible_strikes) <= 21000 else 'SUSPICIOUS'}.")

    # Print a sample around ATM.
    print(f"\nEligible strikes near ATM (18,100-18,300):")
    for s in eligible_strikes:
        if 18100 <= s <= 18300:
            ce, pe = instr_lookup[s]
            print(f"  {int(s):>6}  CE={ce}  PE={pe}")

    print("\nDone.")
