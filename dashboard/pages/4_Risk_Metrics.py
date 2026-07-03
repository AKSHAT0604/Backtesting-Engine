"""Risk-adjusted performance and transaction-cost sensitivity.

Fills a real gap versus a plain daily-PnL view: Sharpe/Sortino/Calmar, win
rate, profit factor, drawdown duration (not just magnitude), rolling Sharpe
over the window, and gross-vs-net PnL under different per-trade cost
assumptions. All of it strategy-aware and window-aware (unlike a one-off
notebook run for a single strategy), computed live from trades.csv /
daily_summary.csv rather than hand-typed into a table.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import data, theme, ui

TRADING_DAYS_PER_YEAR = 252

st.set_page_config(page_title="Risk Metrics", page_icon="\U0001F4CA", layout="wide")
st.title("Risk & Cost Metrics")
st.caption(
    "Risk-adjusted performance and transaction-cost sensitivity — Sharpe, Sortino, "
    "Calmar, drawdown duration, win rate, and profit factor, plus gross-vs-net PnL "
    "under different per-trade cost assumptions."
)

strategy_key = ui.render_strategy_selector()
if not ui.ensure_results_or_prompt(strategy_key):
    st.stop()
st.caption(f"Strategy: **{data.get_strategy_registry()[strategy_key].name}**")

view = ui.render_view_filter(strategy_key)

summary = data.load_daily_summary(strategy_key)
summary = summary[ui.mask_by_view(summary["Date"], view)].sort_values("Date").reset_index(drop=True)
ui.render_view_caption(view)

trades = data.load_trades(strategy_key)
trades = trades[ui.mask_by_view(trades["timestamp"], view)]

if len(summary) < 2:
    st.warning("Need at least 2 trading days in the selected window for risk metrics. "
               "Widen the range in the sidebar.")
    st.stop()


def _risk_metrics(daily_pnl: pd.Series) -> dict:
    """Standard risk-adjusted stats from a daily-PnL series.

    Sharpe/Sortino annualize with sqrt(252); with N well under a year of
    trading days these are noisy point estimates, not reliable standalone
    signals -- surfaced as a caveat in the UI, not hidden.
    """
    n = len(daily_pnl)
    mean = daily_pnl.mean()
    std = daily_pnl.std(ddof=1) if n > 1 else np.nan
    downside = daily_pnl[daily_pnl < 0]
    downside_std = downside.std(ddof=1) if len(downside) > 1 else np.nan

    cum = daily_pnl.cumsum()
    drawdown = cum - cum.cummax()
    max_dd = drawdown.min()

    max_dd_duration, run = 0, 0
    for underwater in (drawdown < 0):
        run = run + 1 if underwater else 0
        max_dd_duration = max(max_dd_duration, run)

    wins = daily_pnl[daily_pnl > 0]
    losses = daily_pnl[daily_pnl < 0]
    win_rate = len(wins) / n if n else np.nan
    profit_factor = (wins.sum() / abs(losses.sum())) if losses.sum() != 0 else np.nan

    sharpe = (mean / std) * np.sqrt(TRADING_DAYS_PER_YEAR) if std else np.nan
    sortino = (mean / downside_std) * np.sqrt(TRADING_DAYS_PER_YEAR) if downside_std else np.nan
    calmar = (mean * TRADING_DAYS_PER_YEAR) / abs(max_dd) if max_dd else np.nan

    return dict(
        total_pnl=daily_pnl.sum(), mean_daily_pnl=mean, std_daily_pnl=std,
        best_day=daily_pnl.max(), worst_day=daily_pnl.min(),
        sharpe=sharpe, sortino=sortino, calmar=calmar,
        max_drawdown=max_dd, max_dd_duration_days=max_dd_duration,
        win_rate=win_rate, profit_factor=profit_factor, trading_days=n,
    )


rows = {
    "NIFTY": _risk_metrics(summary["NIFTY PnL"]),
    "BANKNIFTY": _risk_metrics(summary["BANKNIFTY PnL"]),
    "Combined": _risk_metrics(summary["Total PnL"]),
}
combined = rows["Combined"]

# ---------------------------------------------------------------------------
# Headline KPIs (combined)
# ---------------------------------------------------------------------------
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Sharpe (ann.)", f"{combined['sharpe']:.2f}")
k2.metric("Sortino (ann.)", f"{combined['sortino']:.2f}")
k3.metric("Calmar", f"{combined['calmar']:.2f}")
k4.metric("Win rate", f"{combined['win_rate']:.0%}")
k5.metric("Profit factor", f"{combined['profit_factor']:.2f}")

st.divider()

# ---------------------------------------------------------------------------
# Full metrics table
# ---------------------------------------------------------------------------
st.subheader("Risk-adjusted performance by underlier")
st.caption(
    "Sharpe/Sortino/Calmar are annualized (×√252) from the daily PnL series in the "
    "selected window. With this few trading days these are directional signals, not "
    "precise estimates — the same caveat applies to any short-sample risk-adjusted metric."
)

label_map = {
    "total_pnl": "Total PnL", "mean_daily_pnl": "Mean daily PnL", "std_daily_pnl": "Std daily PnL",
    "best_day": "Best day", "worst_day": "Worst day", "sharpe": "Sharpe (ann.)",
    "sortino": "Sortino (ann.)", "calmar": "Calmar", "max_drawdown": "Max drawdown",
    "max_dd_duration_days": "Max DD duration (days)", "win_rate": "Win rate",
    "profit_factor": "Profit factor", "trading_days": "Trading days",
}
fmt = {
    "Total PnL": "{:,.0f}", "Mean daily PnL": "{:,.1f}", "Std daily PnL": "{:,.1f}",
    "Best day": "{:,.0f}", "Worst day": "{:,.0f}", "Sharpe (ann.)": "{:.2f}",
    "Sortino (ann.)": "{:.2f}", "Calmar": "{:.2f}", "Max drawdown": "{:,.0f}",
    "Max DD duration (days)": "{:.0f}", "Win rate": "{:.1%}", "Profit factor": "{:.2f}",
    "Trading days": "{:.0f}",
}
metrics_df = pd.DataFrame(rows).T.rename(columns=label_map)
st.dataframe(metrics_df.style.format(fmt), width='stretch')

st.divider()

# ---------------------------------------------------------------------------
# Rolling Sharpe -- stability over the window, not one noisy point estimate
# ---------------------------------------------------------------------------
st.subheader("Rolling Sharpe ratio")
st.caption("Whether performance was stable or deteriorating across the window, rather than "
           "collapsing everything into a single point-in-time number.")

max_window = max(3, len(summary) - 1)
window = st.slider("Rolling window (trading days)", min_value=3,
                    max_value=max_window, value=min(5, max_window))

roll_fig = go.Figure()
for label, col in [("NIFTY", "NIFTY PnL"), ("BANKNIFTY", "BANKNIFTY PnL")]:
    s = summary[col]
    roll_sharpe = (s.rolling(window).mean() / s.rolling(window).std(ddof=1)) * np.sqrt(TRADING_DAYS_PER_YEAR)
    roll_fig.add_trace(go.Scatter(
        x=summary["Date"], y=roll_sharpe, name=label, mode="lines",
        line=dict(color=theme.underlier_color(label), width=2),
        hovertemplate="%{x|%b %d}<br>" + label + ": %{y:.2f}<extra></extra>",
    ))
theme.apply_base_layout(roll_fig, y_title=f"{window}-day rolling Sharpe", height=380)
st.plotly_chart(roll_fig, width='stretch')

st.divider()

# ---------------------------------------------------------------------------
# Transaction cost sensitivity
# ---------------------------------------------------------------------------
st.subheader("Transaction cost sensitivity")
st.caption(
    "The strategy rolls frequently, so even a small per-trade cost compounds. Notional "
    "is Σ(price × quantity) across every executed leg in the window; cost drag is that "
    "notional times the assumed cost in basis points, subtracted from gross PnL."
)

notional = float((trades["price"] * trades["quantity"]).sum())
gross_pnl = float(summary["Total PnL"].sum())

cc1, cc2 = st.columns(2)
cc1.metric("Total notional traded", f"{notional:,.0f}")
cc2.metric("Legs executed", f"{len(trades):,}")

bps_options = [0, 1, 2, 5, 10, 20]
cost_df = pd.DataFrame([
    {"Cost (bps)": bps, "Notional traded": notional, "Cost drag": notional * bps / 10000,
     "Gross PnL": gross_pnl, "Net PnL": gross_pnl - notional * bps / 10000}
    for bps in bps_options
])

pos_color, neg_color = theme.polarity_colors()
cost_fig = go.Figure()
cost_fig.add_trace(go.Scatter(
    x=cost_df["Cost (bps)"], y=cost_df["Net PnL"], mode="lines+markers",
    line=dict(color=pos_color if gross_pnl >= 0 else neg_color, width=2),
    marker=dict(size=8, color=theme.pnl_bar_colors(cost_df["Net PnL"])),
    hovertemplate="%{x} bps<br>Net PnL: %{y:,.0f}<extra></extra>",
))
cost_fig.add_hline(y=0, line_dash="dot", line_color=theme.muted_color(), opacity=0.6)
theme.apply_base_layout(cost_fig, x_title="Assumed cost (bps per trade)", y_title="Net PnL",
                         show_legend=False, height=340)
st.plotly_chart(cost_fig, width='stretch')

st.dataframe(
    cost_df.style.format({"Notional traded": "{:,.0f}", "Cost drag": "{:,.0f}",
                           "Gross PnL": "{:,.0f}", "Net PnL": "{:,.0f}"}),
    hide_index=True, width='stretch',
)

st.divider()

# ---------------------------------------------------------------------------
# Reading these numbers
# ---------------------------------------------------------------------------
st.subheader("Reading these numbers")
worst_case_drag = notional * bps_options[-1] / 10000
flips_sign = (gross_pnl > 0) != (gross_pnl - worst_case_drag > 0)
st.markdown(f"""
- Sharpe/Sortino/Calmar are annualized from only **{combined['trading_days']} trading days**
  in this window — read them as directional, not precise.
- The strategy was profitable on **{combined['win_rate']:.0%}** of days, with a profit
  factor of **{combined['profit_factor']:.2f}**
  ({'winning days more than cover losing days' if combined['profit_factor'] > 1 else 'losing days outweigh what winning days make back'}).
- Longest continuous drawdown: **{combined['max_dd_duration_days']:.0f} of {combined['trading_days']}**
  days underwater from the running peak.
- At **{bps_options[-1]} bps** per trade, transaction costs alone would move net PnL by
  **{worst_case_drag:,.0f}** — {'enough to flip the sign of the result' if flips_sign else 'a material drag, but not enough on its own to flip the sign of the result'}.
""")
