"""Cached, strategy-aware data access for the analysis portal.

Every backtest artifact is now namespaced per strategy under
    results/strategies/<strategy_key>/
so the dashboard can switch strategies just by changing the key it loads. The
list of strategies comes straight from the engine's `strategies/` registry, so
adding a strategy file makes it appear here with no dashboard edits.

Two tiers:
  1. Precomputed per-strategy results (results/strategies/<key>/*.csv).
  2. Raw per-day ticks (Data/allData/...), strategy-independent, loaded on
     demand for day-level drilldowns.
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

APP_DIR = Path(__file__).resolve().parent.parent          # .../dashboard
ENGINE_DIR = APP_DIR.parent                                # .../Backtesting-Engine
ENGINE_CODE_DIR = ENGINE_DIR / "engine"                    # importable engine modules
RESULTS_DIR = ENGINE_DIR / "results"
STRATEGIES_RESULTS_DIR = RESULTS_DIR / "strategies"

if str(ENGINE_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_CODE_DIR))

from futures_loader import load_futures_file  # noqa: E402  (reuse existing loader)
from strategies import get_registry            # noqa: E402  (strategy registry)
from data_paths import resolve_data_root       # noqa: E402  (shared data-root resolver)

DATA_ROOT = resolve_data_root()
DEFAULT_STRATEGY = "closest_strike_straddle"


# ---------------------------------------------------------------------------
# Strategy registry / availability
# ---------------------------------------------------------------------------

def get_strategy_registry():
    """All registered strategies {key: StrategyInfo} from the engine package."""
    return get_registry()


def strategy_dir(strategy_key: str) -> Path:
    return STRATEGIES_RESULTS_DIR / strategy_key


def strategy_results_available(strategy_key: str) -> bool:
    d = strategy_dir(strategy_key)
    return all((d / f).is_file() for f in
               ("trades.csv", "positions_timeline.csv", "mtm_timeline.csv", "daily_summary.csv"))


def clear_caches() -> None:
    st.cache_data.clear()


# ---------------------------------------------------------------------------
# Tier 1 — precomputed per-strategy results
# ---------------------------------------------------------------------------

@st.cache_data
def load_trades(strategy_key: str) -> pd.DataFrame:
    df = pd.read_csv(strategy_dir(strategy_key) / "trades.csv")
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    if "option_type" not in df.columns:
        df["option_type"] = df["instrument_name"].str[-2:]
    return df


@st.cache_data
def load_positions(strategy_key: str) -> pd.DataFrame:
    df = pd.read_csv(strategy_dir(strategy_key) / "positions_timeline.csv")
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


@st.cache_data
def load_mtm(strategy_key: str) -> pd.DataFrame:
    df = pd.read_csv(strategy_dir(strategy_key) / "mtm_timeline.csv")
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


@st.cache_data
def load_daily_summary_raw(strategy_key: str) -> pd.DataFrame:
    """The DELIVERABLES.md D6 schema: one row per (trade_date, underlier)."""
    df = pd.read_csv(strategy_dir(strategy_key) / "daily_summary.csv")
    return df


@st.cache_data
def load_daily_summary(strategy_key: str) -> pd.DataFrame:
    """Wide, per-date view derived from the D6 summary (what most pages want).

    Columns: Date, Total PnL, NIFTY PnL, BANKNIFTY PnL, NIFTY Rolls,
    BANKNIFTY Rolls, Total Trades Executed (Rolls), Cumulative PnL.
    """
    raw = load_daily_summary_raw(strategy_key)
    pnl = raw.pivot(index="trade_date", columns="underlier", values="gross_pnl").fillna(0.0)
    rolls = raw.pivot(index="trade_date", columns="underlier", values="num_rolls").fillna(0).astype(int)

    out = pd.DataFrame({"trade_date": pnl.index})
    out["NIFTY PnL"] = pnl.get("NIFTY", 0.0).values
    out["BANKNIFTY PnL"] = pnl.get("BANKNIFTY", 0.0).values
    out["Total PnL"] = out["NIFTY PnL"] + out["BANKNIFTY PnL"]
    out["NIFTY Rolls"] = rolls.get("NIFTY", 0).values
    out["BANKNIFTY Rolls"] = rolls.get("BANKNIFTY", 0).values
    out["Total Trades Executed (Rolls)"] = out["NIFTY Rolls"] + out["BANKNIFTY Rolls"]
    out["Date"] = pd.to_datetime(out["trade_date"])
    out = out.sort_values("Date").reset_index(drop=True)
    out["Cumulative PnL"] = out["Total PnL"].cumsum()
    return out


def get_trade_dates(strategy_key: str) -> list[str]:
    return sorted(load_daily_summary(strategy_key)["Date"].dt.strftime("%Y-%m-%d").tolist())


@st.cache_data
def get_full_cumulative_mtm(strategy_key: str) -> pd.DataFrame:
    """Second-resolution cumulative PnL across the whole month.

    mtm_timeline resets each day (no cross-day position), so the running month
    total is that day's series plus every prior day's closing total.
    """
    mtm = load_mtm(strategy_key).copy()
    summary = load_daily_summary(strategy_key)
    daily_final = dict(zip(summary["Date"].dt.strftime("%Y-%m-%d"), summary["Total PnL"]))
    nifty_final = dict(zip(summary["Date"].dt.strftime("%Y-%m-%d"), summary["NIFTY PnL"]))
    bn_final = dict(zip(summary["Date"].dt.strftime("%Y-%m-%d"), summary["BANKNIFTY PnL"]))

    dates = sorted(mtm["trade_date"].dropna().unique())
    offset = nifty_offset = bn_offset = 0.0
    parts = []
    for d in dates:
        day = mtm[mtm["trade_date"] == d].copy()
        day["cumulative_pnl"] = day["combined_total_pnl"] + offset
        day["nifty_cumulative"] = day["nifty_total_pnl"] + nifty_offset
        day["banknifty_cumulative"] = day["banknifty_total_pnl"] + bn_offset
        parts.append(day)
        offset += daily_final.get(d, 0.0)
        nifty_offset += nifty_final.get(d, 0.0)
        bn_offset += bn_final.get(d, 0.0)
    return pd.concat(parts, ignore_index=True)


# ---------------------------------------------------------------------------
# Derived analytics
# ---------------------------------------------------------------------------

@st.cache_data
def leg_pnl_summary(strategy_key: str) -> pd.DataFrame:
    """Realized PnL per closed leg, tagged by underlier and option type.

    BUY/SELL strictly alternate per (trade_date, instrument_name), so pairing
    the i-th BUY with the i-th SELL in timestamp order recovers each closed leg.
    """
    trades = load_trades(strategy_key).sort_values(["trade_date", "instrument_name", "timestamp"])
    rows = []
    for (trade_date, instrument), grp in trades.groupby(["trade_date", "instrument_name"], sort=False):
        buys = grp[grp["direction"] == "BUY"].reset_index(drop=True)
        sells = grp[grp["direction"] == "SELL"].reset_index(drop=True)
        n = min(len(buys), len(sells))
        if n == 0:
            continue
        pnl = sells["price"].iloc[:n].to_numpy() - buys["price"].iloc[:n].to_numpy()
        rows.append(pd.DataFrame({
            "trade_date": trade_date,
            "underlier": grp["underlier"].iloc[0],
            "option_type": instrument[-2:],
            "instrument_name": instrument,
            "entry_time": buys["timestamp"].iloc[:n].to_numpy(),
            "exit_time": sells["timestamp"].iloc[:n].to_numpy(),
            "realized_pnl": pnl,
        }))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["trade_date", "underlier", "option_type", "instrument_name",
                 "entry_time", "exit_time", "realized_pnl"])


@st.cache_data
def holding_durations(strategy_key: str) -> pd.DataFrame:
    """Seconds each HOLDING row stayed live, per underlier/day."""
    pos = load_positions(strategy_key).sort_values(["trade_date", "underlier", "timestamp"]).copy()
    pos["next_timestamp"] = pos.groupby(["trade_date", "underlier"])["timestamp"].shift(-1)
    holding = pos[pos["state"] == "HOLDING"].copy()
    holding["duration_sec"] = (holding["next_timestamp"] - holding["timestamp"]).dt.total_seconds()
    return holding.dropna(subset=["duration_sec"])


@st.cache_data
def turnover_by_hour(strategy_key: str) -> pd.DataFrame:
    trades = load_trades(strategy_key).copy()
    trades["hour"] = trades["timestamp"].dt.hour
    return (trades.groupby(["trade_date", "hour"]).size()
            .reset_index(name="trade_count"))


@st.cache_data
def rolls_per_day_by_underlier(strategy_key: str) -> pd.DataFrame:
    positions = load_positions(strategy_key)
    rolls = positions[positions["trigger"] == "ROLL"]
    return (rolls.groupby(["trade_date", "underlier"]).size()
            .reset_index(name="rolls"))


# ---------------------------------------------------------------------------
# Tier 2 — raw per-day ticks (strategy-independent)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def load_day_futures(trade_date: str, underlier: str) -> pd.DataFrame:
    folder = "NSE_" + trade_date.replace("-", "")
    path = DATA_ROOT / folder / "Futures (Continuous)" / f"{underlier}-I.csv"
    if not path.is_file():
        return pd.DataFrame(columns=["timestamp", "price"])
    df = load_futures_file(path, trade_date, underlier)
    return df[["timestamp", "price"]]


@st.cache_data(show_spinner=False)
def load_day_instrument(trade_date: str, instrument_name: str) -> pd.DataFrame:
    folder = "NSE_" + trade_date.replace("-", "")
    path = DATA_ROOT / folder / "Options" / f"{instrument_name}.csv"
    if not path.is_file():
        return pd.DataFrame(columns=["timestamp", "price"])
    df = load_futures_file(path, trade_date, instrument_name)
    return df[["timestamp", "price"]]


def raw_data_available() -> bool:
    return DATA_ROOT.is_dir()
