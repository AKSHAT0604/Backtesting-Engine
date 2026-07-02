"""
reporting.py — Output shaping to the DELIVERABLES.md schemas (fixes finding D).

Two responsibilities:
  * enrich_trades  — add expiry / strike / option_type columns to trades so a
    reader never has to re-parse the instrument name (DELIVERABLES.md D3).
  * build_daily_summary — the D6 schema: one row per (trade_date, underlier)
    with trade/roll counts, EOD PnL, first-entry / last-roll times, churn, and
    max favorable/adverse excursion.

Roll counting note: rolls are counted as strike-change events from the
positions timeline (trigger == "ROLL"), not as trade-fill quartets. Under
ASSUMPTIONS.md A5 a strike change whose new legs are unpriced becomes an exit
now + a re-entry later, so fills are no longer a clean multiple of 4 — the
positions view is the robust source of truth for "how many times did we roll."
"""

from __future__ import annotations

import pandas as pd

from option_filename_parser import parse_option_filename

# Canonical column orders.
TRADES_COLS = [
    "trade_date", "timestamp", "underlier", "expiry", "strike", "option_type",
    "instrument_name", "direction", "price", "quantity", "reason",
]
DAILY_SUMMARY_COLS = [
    "trade_date", "underlier", "num_trades", "num_entries", "num_rolls",
    "num_squareoffs", "gross_pnl", "first_entry_time", "last_roll_time",
    "num_unique_strikes_held", "max_favorable_excursion", "max_adverse_excursion",
]


def enrich_trades(trades_df: pd.DataFrame) -> pd.DataFrame:
    """Add expiry, strike, option_type (parsed from instrument_name) to trades."""
    if trades_df.empty:
        return pd.DataFrame(columns=TRADES_COLS)

    df = trades_df.copy()
    parsed = df["instrument_name"].apply(lambda n: parse_option_filename(f"{n}.csv"))
    df["expiry"] = parsed.apply(lambda p: p["expiry_date"])
    df["strike"] = parsed.apply(lambda p: p["strike"])
    df["option_type"] = parsed.apply(lambda p: p["option_type"])

    # Any columns the caller didn't provide default to sensible values.
    for col in TRADES_COLS:
        if col not in df.columns:
            df[col] = None
    return df[TRADES_COLS]


def _underlier_pnl_column(underlier: str) -> str:
    return f"{underlier.lower()}_total_pnl"


def build_daily_summary(
    trades_df: pd.DataFrame,
    mtm_df: pd.DataFrame,
    positions_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build the DELIVERABLES.md D6 daily summary: one row per (date, underlier)."""
    dates = sorted(mtm_df["trade_date"].dropna().unique())
    underliers = ["NIFTY", "BANKNIFTY"]
    rows: list[dict] = []

    for trade_date in dates:
        day_mtm = mtm_df[mtm_df["trade_date"] == trade_date]
        for underlier in underliers:
            pnl_col = _underlier_pnl_column(underlier)
            series = day_mtm[pnl_col].dropna() if pnl_col in day_mtm.columns else pd.Series(dtype=float)

            t = trades_df[(trades_df["trade_date"] == trade_date)
                          & (trades_df["underlier"] == underlier)]
            p = positions_df[(positions_df["trade_date"] == trade_date)
                             & (positions_df["underlier"] == underlier)]

            entry_fills = t[t["reason"] == "ENTRY"]
            roll_events = p[p["trigger"] == "ROLL"]
            held = p[p["state"] == "HOLDING"]

            first_entry_time = (
                pd.to_datetime(entry_fills["timestamp"]).min().strftime("%H:%M:%S")
                if not entry_fills.empty else None
            )
            last_roll_time = (
                pd.to_datetime(roll_events["timestamp"]).max().strftime("%H:%M:%S")
                if not roll_events.empty else None
            )

            rows.append({
                "trade_date": trade_date,
                "underlier": underlier,
                "num_trades": int(len(t)),
                "num_entries": int((t["reason"] == "ENTRY").sum()),
                "num_rolls": int(len(roll_events)),
                "num_squareoffs": int((t["reason"] == "SQUAREOFF").sum()),
                "gross_pnl": float(series.iloc[-1]) if not series.empty else 0.0,
                "first_entry_time": first_entry_time,
                "last_roll_time": last_roll_time,
                "num_unique_strikes_held": int(held["strike"].nunique()),
                "max_favorable_excursion": float(series.max()) if not series.empty else 0.0,
                "max_adverse_excursion": float(series.min()) if not series.empty else 0.0,
            })

    return pd.DataFrame(rows, columns=DAILY_SUMMARY_COLS)
