"""
generate_report_assets.py — One-off script: prints the headline numbers used
in README.md's results narrative and renders the static chart images embedded
there (docs/report_assets/*.png). Not part of the pipeline or the dashboard —
purely a report-authoring aid, kept for reproducibility of the report's figures.

Usage:
    python generate_report_assets.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "engine"))
from data_paths import results_dir  # noqa: E402

RESULTS_DIR = results_dir()
STRATEGY = "closest_strike_straddle"
STRAT_DIR = RESULTS_DIR / "strategies" / STRATEGY
ASSETS_DIR = Path(__file__).resolve().parent / "docs" / "report_assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# Palette -- matches dashboard/lib/theme.py exactly, hardcoded here to keep
# this script decoupled from Streamlit.
BLUE, AQUA, RED = "#2a78d6", "#1baf7a", "#e34948"
VIOLET, ORANGE = "#4a3aa7", "#eb6834"
INK, MUTED, GRID = "#0b0b0b", "#767468", "#e1e0d9"

plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white",
    "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "grid.color": GRID,
    "font.family": "sans-serif", "axes.spines.top": False, "axes.spines.right": False,
})


def load():
    trades = pd.read_csv(STRAT_DIR / "trades.csv", parse_dates=["timestamp"])
    positions = pd.read_csv(STRAT_DIR / "positions_timeline.csv", parse_dates=["timestamp"])
    mtm = pd.read_csv(STRAT_DIR / "mtm_timeline.csv", parse_dates=["timestamp"])
    summary_raw = pd.read_csv(STRAT_DIR / "daily_summary.csv")
    return trades, positions, mtm, summary_raw


def wide_summary(summary_raw: pd.DataFrame) -> pd.DataFrame:
    pnl = summary_raw.pivot(index="trade_date", columns="underlier", values="gross_pnl").fillna(0.0)
    rolls = summary_raw.pivot(index="trade_date", columns="underlier", values="num_rolls").fillna(0).astype(int)
    out = pd.DataFrame({"trade_date": pnl.index})
    out["NIFTY PnL"] = pnl.get("NIFTY", 0.0).values
    out["BANKNIFTY PnL"] = pnl.get("BANKNIFTY", 0.0).values
    out["Total PnL"] = out["NIFTY PnL"] + out["BANKNIFTY PnL"]
    out["NIFTY Rolls"] = rolls.get("NIFTY", 0).values
    out["BANKNIFTY Rolls"] = rolls.get("BANKNIFTY", 0).values
    out["Total Rolls"] = out["NIFTY Rolls"] + out["BANKNIFTY Rolls"]
    out["Date"] = pd.to_datetime(out["trade_date"])
    out = out.sort_values("Date").reset_index(drop=True)
    out["Cumulative PnL"] = out["Total PnL"].cumsum()
    return out


def full_cumulative_mtm(mtm: pd.DataFrame, summary: pd.DataFrame) -> pd.DataFrame:
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


def leg_pnl(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (trade_date, instrument), grp in trades.sort_values("timestamp").groupby(
        ["trade_date", "instrument_name"], sort=False
    ):
        buys = grp[grp["direction"] == "BUY"].reset_index(drop=True)
        sells = grp[grp["direction"] == "SELL"].reset_index(drop=True)
        n = min(len(buys), len(sells))
        if n == 0:
            continue
        pnl = sells["price"].iloc[:n].to_numpy() - buys["price"].iloc[:n].to_numpy()
        rows.append(pd.DataFrame({
            "underlier": grp["underlier"].iloc[0],
            "option_type": instrument[-2:],
            "realized_pnl": pnl,
        }))
    return pd.concat(rows, ignore_index=True)


def savefig(fig, name):
    path = ASSETS_DIR / name
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  saved {path.relative_to(Path(__file__).resolve().parent)}")


def main():
    trades, positions, mtm, summary_raw = load()
    summary = wide_summary(summary_raw)
    cum = full_cumulative_mtm(mtm, summary)
    legs = leg_pnl(trades)
    holding = positions[positions["state"] == "HOLDING"].sort_values(
        ["trade_date", "underlier", "timestamp"]
    ).copy()
    holding["next_timestamp"] = holding.groupby(["trade_date", "underlier"])["timestamp"].shift(-1)
    holding["duration_sec"] = (holding["next_timestamp"] - holding["timestamp"]).dt.total_seconds()
    holding = holding.dropna(subset=["duration_sec"])

    # ---- Print headline numbers for the README narrative --------------------
    print("=" * 70)
    print("HEADLINE NUMBERS")
    print("=" * 70)
    total_pnl = summary["Total PnL"].sum()
    total_rolls = int(summary["Total Rolls"].sum())
    n_days = len(summary)
    best = summary.loc[summary["Total PnL"].idxmax()]
    worst = summary.loc[summary["Total PnL"].idxmin()]
    win_days = int((summary["Total PnL"] > 0).sum())
    nifty_rolls = int(summary["NIFTY Rolls"].sum())
    bn_rolls = int(summary["BANKNIFTY Rolls"].sum())
    nifty_pnl = summary["NIFTY PnL"].sum()
    bn_pnl = summary["BANKNIFTY PnL"].sum()
    by_leg = legs.groupby("option_type")["realized_pnl"].sum().reindex(["CE", "PE"]).fillna(0)
    running_peak = cum["cumulative_pnl"].cummax()
    max_dd = (cum["cumulative_pnl"] - running_peak).min()
    top3 = summary.nlargest(3, "Total PnL")["Total PnL"].sum()
    positive_total = summary.loc[summary["Total PnL"] > 0, "Total PnL"].sum()
    concentration = (top3 / positive_total * 100) if positive_total else 0

    print(f"trading days               : {n_days}")
    print(f"total fills (trades.csv)   : {len(trades):,}")
    print(f"total rolls                : {total_rolls:,}  (NIFTY {nifty_rolls:,} / BANKNIFTY {bn_rolls:,})")
    print(f"avg rolls/day              : {total_rolls / n_days:.1f}")
    print(f"month total PnL            : {total_pnl:,.2f}")
    print(f"  NIFTY PnL                : {nifty_pnl:,.2f}")
    print(f"  BANKNIFTY PnL            : {bn_pnl:,.2f}")
    print(f"avg daily PnL              : {total_pnl / n_days:,.2f}")
    print(f"positive-PnL days          : {win_days} / {n_days}")
    print(f"best day                   : {best['Date'].date()}  {best['Total PnL']:+.2f}")
    print(f"worst day                  : {worst['Date'].date()}  {worst['Total PnL']:+.2f}")
    print(f"CE realized PnL            : {by_leg['CE']:,.2f}")
    print(f"PE realized PnL            : {by_leg['PE']:,.2f}")
    print(f"max drawdown               : {max_dd:,.2f}")
    print(f"top-3-day PnL concentration: {concentration:.1f}% of positive PnL")
    print(f"median holding duration    : {holding['duration_sec'].median():.0f}s "
          f"(NIFTY {holding[holding.underlier=='NIFTY']['duration_sec'].median():.0f}s, "
          f"BANKNIFTY {holding[holding.underlier=='BANKNIFTY']['duration_sec'].median():.0f}s)")

    # ---- Charts ---------------------------------------------------------
    print("\n" + "=" * 70)
    print("GENERATING CHART IMAGES")
    print("=" * 70)

    # 1. Cumulative PnL
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(cum["timestamp"], cum["cumulative_pnl"], color=BLUE, lw=1.5)
    ax.fill_between(cum["timestamp"], cum["cumulative_pnl"], 0, color=BLUE, alpha=0.08)
    ax.axhline(0, color=GRID, lw=1)
    ax.set_title("Cumulative mark-to-market PnL — November 2022", fontsize=13, fontweight="bold", color=INK)
    ax.set_ylabel("PnL")
    ax.grid(axis="y", alpha=0.6)
    savefig(fig, "01_cumulative_pnl.png")

    # 2. Daily PnL bar
    fig, ax = plt.subplots(figsize=(10, 4.5))
    colors = [BLUE if v >= 0 else RED for v in summary["Total PnL"]]
    ax.bar(summary["Date"].dt.strftime("%m-%d"), summary["Total PnL"], color=colors)
    ax.axhline(0, color=INK, lw=1)
    ax.set_title("Daily PnL", fontsize=13, fontweight="bold", color=INK)
    ax.set_ylabel("PnL")
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    ax.grid(axis="y", alpha=0.6)
    savefig(fig, "02_daily_pnl.png")

    # 3. Rolls per day by underlier
    fig, ax = plt.subplots(figsize=(10, 4.5))
    x = np.arange(len(summary))
    w = 0.38
    ax.bar(x - w / 2, summary["NIFTY Rolls"], width=w, color=BLUE, label="NIFTY")
    ax.bar(x + w / 2, summary["BANKNIFTY Rolls"], width=w, color=AQUA, label="BANKNIFTY")
    ax.set_xticks(x)
    ax.set_xticklabels(summary["Date"].dt.strftime("%m-%d"), rotation=45, ha="right")
    ax.set_title("Rolls executed per day, by underlier", fontsize=13, fontweight="bold", color=INK)
    ax.set_ylabel("Rolls")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.6)
    savefig(fig, "03_rolls_per_day.png")

    # 4. Holding duration distribution
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for underlier, color in (("NIFTY", BLUE), ("BANKNIFTY", AQUA)):
        d = holding.loc[holding["underlier"] == underlier, "duration_sec"]
        cap = np.percentile(d, 98)
        ax.hist(d[d <= cap], bins=60, alpha=0.6, color=color, label=underlier)
    ax.set_title("Holding-duration distribution (clipped at 98th percentile)",
                 fontsize=13, fontweight="bold", color=INK)
    ax.set_xlabel("Seconds held before roll / square-off")
    ax.set_ylabel("Count")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.6)
    savefig(fig, "04_holding_duration.png")

    # 5. CE vs PE realized PnL (horizontal bar — same fix as the dashboard)
    fig, ax = plt.subplots(figsize=(8, 3.2))
    ax.barh(by_leg.index, by_leg.values, color=[VIOLET, ORANGE])
    ax.axvline(0, color=INK, lw=1)
    ax.set_title("Realized PnL by leg type", fontsize=13, fontweight="bold", color=INK)
    ax.set_xlabel("PnL")
    ax.grid(axis="x", alpha=0.6)
    savefig(fig, "05_ce_vs_pe.png")

    # 6. NIFTY vs BANKNIFTY cumulative
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(cum["timestamp"], cum["nifty_cumulative"], color=BLUE, lw=1.5, label="NIFTY")
    ax.plot(cum["timestamp"], cum["banknifty_cumulative"], color=AQUA, lw=1.5, label="BANKNIFTY")
    ax.axhline(0, color=GRID, lw=1)
    ax.set_title("Cumulative PnL — NIFTY vs BANKNIFTY", fontsize=13, fontweight="bold", color=INK)
    ax.set_ylabel("PnL")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.6)
    savefig(fig, "06_nifty_vs_banknifty.png")

    # 7. Drawdown curve
    fig, ax = plt.subplots(figsize=(10, 3.8))
    drawdown = cum["cumulative_pnl"] - running_peak
    ax.plot(cum["timestamp"], drawdown, color=RED, lw=1.2)
    ax.fill_between(cum["timestamp"], drawdown, 0, color=RED, alpha=0.12)
    ax.set_title(f"Drawdown from running peak (max {max_dd:,.0f})", fontsize=13, fontweight="bold", color=INK)
    ax.set_ylabel("Drawdown")
    ax.grid(axis="y", alpha=0.6)
    savefig(fig, "07_drawdown.png")

    # 8. Sample-day intraday MTM with roll markers (2022-11-01, the manually
    #    reconciled validation day)
    sample_date = "2022-11-01"
    day_mtm = mtm[mtm["trade_date"] == sample_date].sort_values("timestamp")
    day_pos = positions[(positions["trade_date"] == sample_date)]
    roll_times = day_pos.loc[day_pos["trigger"] == "ROLL", "timestamp"]
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(day_mtm["timestamp"], day_mtm["nifty_total_pnl"], color=BLUE, lw=1.3, label="NIFTY")
    ax.plot(day_mtm["timestamp"], day_mtm["banknifty_total_pnl"], color=AQUA, lw=1.3, label="BANKNIFTY")
    ax.plot(day_mtm["timestamp"], day_mtm["combined_total_pnl"], color=INK, lw=1.3, ls=":", label="Combined")
    for t in roll_times.sample(min(40, len(roll_times)), random_state=0).sort_values():
        ax.axvline(t, color=MUTED, lw=0.5, alpha=0.35)
    ax.set_title(f"Intraday MTM — {sample_date} (thin lines mark a sample of roll events)",
                 fontsize=13, fontweight="bold", color=INK)
    ax.set_ylabel("PnL")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.6)
    savefig(fig, "08_sample_day_intraday_mtm.png")

    # 9. Futures vs. selected strike, same sample day, NIFTY
    futures_path = RESULTS_DIR / "futures_intraday.parquet"
    if futures_path.is_file():
        fut_all = pd.read_parquet(futures_path)
        fut_all["timestamp"] = pd.to_datetime(fut_all["timestamp"])
        fut = fut_all[(fut_all["trade_date"] == sample_date) & (fut_all["underlier"] == "NIFTY")]
        strike_steps = day_pos[day_pos["underlier"] == "NIFTY"][["timestamp", "strike"]].dropna()
        strike_series = pd.merge_asof(fut[["timestamp"]].sort_values("timestamp"),
                                       strike_steps.sort_values("timestamp"),
                                       on="timestamp", direction="backward")
        fig, ax = plt.subplots(figsize=(10, 4.5))
        ax.plot(fut["timestamp"], fut["price"], color=BLUE, lw=1.5, label="Futures price")
        ax.step(strike_series["timestamp"], strike_series["strike"], color=INK, lw=1.2,
                ls=":", where="post", label="Selected (closest) strike")
        ax.set_title(f"Futures price vs. selected strike — NIFTY, {sample_date}",
                     fontsize=13, fontweight="bold", color=INK)
        ax.set_ylabel("Price")
        ax.legend(frameon=False)
        ax.grid(axis="y", alpha=0.6)
        savefig(fig, "09_futures_vs_strike.png")
    else:
        print("  skipped 09_futures_vs_strike.png (run export_market_data.py first)")

    print("\nDone.")


if __name__ == "__main__":
    main()
