import plotly.graph_objects as go
import streamlit as st

from lib import data, theme, ui

st.set_page_config(page_title="Options Backtest Portal", page_icon="\U0001F4C8", layout="wide")

st.title("NSE Options Backtest — Analysis Portal")
st.caption(
    "Intraday options backtest, NIFTY & BANKNIFTY, November 2022. Pick a strategy "
    "in the sidebar; click any bar in the daily PnL chart to drill into that day."
)

strategy_key = ui.render_strategy_selector()
if not ui.ensure_results_or_prompt(strategy_key):
    st.stop()

view = ui.render_view_filter(strategy_key)

registry = data.get_strategy_registry()
st.subheader(registry[strategy_key].name)
st.caption(registry[strategy_key].description)

summary = data.load_daily_summary(strategy_key)
summary = summary[ui.mask_by_view(summary["Date"], view)]
ui.render_view_caption(view)

if summary.empty:
    st.warning("No trading days fall inside the selected window. Widen the range in the sidebar.")
    st.stop()

# ---------------------------------------------------------------------------
# KPI row
# ---------------------------------------------------------------------------
total_pnl = summary["Total PnL"].sum()
total_rolls = int(summary["Total Trades Executed (Rolls)"].sum())
best_day = summary.loc[summary["Total PnL"].idxmax()]
worst_day = summary.loc[summary["Total PnL"].idxmin()]
win_days = (summary["Total PnL"] > 0).sum()

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total PnL (window)", f"{total_pnl:,.0f}")
c2.metric("Total rolls executed", f"{total_rolls:,}")
c3.metric("Positive-PnL days", f"{win_days} / {len(summary)}")
c4.metric("Best day", best_day["Date"].strftime("%b %d"), f"{best_day['Total PnL']:+.0f}")
c5.metric("Worst day", worst_day["Date"].strftime("%b %d"), f"{worst_day['Total PnL']:+.0f}")

st.divider()

# ---------------------------------------------------------------------------
# Cumulative PnL (second resolution, filtered window)
# ---------------------------------------------------------------------------
st.subheader("Cumulative mark-to-market PnL")
cum = data.get_full_cumulative_mtm(strategy_key)
cum = cum[ui.mask_by_view(cum["timestamp"], view)]

fig = go.Figure()
fig.add_trace(go.Scatter(
    x=cum["timestamp"], y=cum["cumulative_pnl"],
    mode="lines", line=dict(color=theme.polarity_colors()[0], width=2),
    fill="tozeroy", fillcolor="rgba(42,120,214,0.08)",
    name="Cumulative PnL",
    hovertemplate="%{x|%d %b %H:%M}<br>PnL: %{y:,.0f}<extra></extra>",
))
theme.apply_base_layout(fig, y_title="PnL", show_legend=False, height=380)
st.plotly_chart(fig, width='stretch')

# ---------------------------------------------------------------------------
# Daily PnL — click a bar to drill into that day
# ---------------------------------------------------------------------------
st.subheader("Daily PnL — click a bar to drill in")
dates_str = summary["Date"].dt.strftime("%Y-%m-%d")
bar_fig = go.Figure()
bar_fig.add_trace(go.Bar(
    x=dates_str, y=summary["Total PnL"],
    marker_color=theme.pnl_bar_colors(summary["Total PnL"]),
    hovertemplate="%{x}<br>PnL: %{y:,.0f}<extra></extra>",
    name="Daily PnL",
))
theme.apply_base_layout(bar_fig, y_title="PnL", x_title=None, show_legend=False, height=360)

event = st.plotly_chart(bar_fig, width='stretch', on_select="rerun", key="daily_pnl_chart")

clicked_date = None
if event and event.get("selection", {}).get("points"):
    clicked_date = event["selection"]["points"][0]["x"]

if clicked_date:
    st.session_state["selected_date"] = clicked_date
    row = summary[dates_str == clicked_date].iloc[0]
    st.success(
        f"Selected **{clicked_date}** — Total PnL {row['Total PnL']:+.2f}, "
        f"{int(row['Total Trades Executed (Rolls)'])} rolls."
    )
    st.page_link("pages/1_Day_Drilldown.py", label="Open Day Drilldown →", icon="\U0001F50E")
else:
    st.info("Click a bar above, or pick a date directly on the Day Drilldown page.")

st.divider()

# ---------------------------------------------------------------------------
# Rolls per day by underlier
# ---------------------------------------------------------------------------
st.subheader("Rolls executed per day, by underlier")
roll_fig = go.Figure()
roll_fig.add_trace(go.Bar(x=dates_str, y=summary["NIFTY Rolls"], name="NIFTY",
                           marker_color=theme.underlier_color("NIFTY"),
                           hovertemplate="%{x}<br>NIFTY rolls: %{y}<extra></extra>"))
roll_fig.add_trace(go.Bar(x=dates_str, y=summary["BANKNIFTY Rolls"], name="BANKNIFTY",
                           marker_color=theme.underlier_color("BANKNIFTY"),
                           hovertemplate="%{x}<br>BANKNIFTY rolls: %{y}<extra></extra>"))
roll_fig.update_layout(barmode="group")
theme.apply_base_layout(roll_fig, y_title="Rolls", height=340)
st.plotly_chart(roll_fig, width='stretch')

# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------
st.subheader("Key findings")
nifty_turnover = int(summary["NIFTY Rolls"].sum())
bn_turnover = int(summary["BANKNIFTY Rolls"].sum())
higher_turnover = "BANKNIFTY" if bn_turnover > nifty_turnover else "NIFTY"
top3 = summary.nlargest(3, "Total PnL")["Total PnL"].sum()
positive_total = summary.loc[summary["Total PnL"] > 0, "Total PnL"].sum()
concentration = (top3 / positive_total * 100) if positive_total > 0 else 0
churniest = summary.loc[summary["Total Trades Executed (Rolls)"].idxmax()]

st.markdown(f"""
- The strategy executed **{total_rolls:,} rolls** over {len(summary)} trading days (avg {total_rolls/len(summary):.1f}/day).
- **{higher_turnover}** had the higher overall turnover (NIFTY: {nifty_turnover}, BANKNIFTY: {bn_turnover}).
- The top 3 days contributed **{concentration:.1f}%** of total positive PnL — {'gains are concentrated in a few days' if concentration > 50 else 'gains are fairly spread out'}.
- Highest single-day churn: **{churniest['Date'].strftime('%b %d')}** with {int(churniest['Total Trades Executed (Rolls)'])} rolls.
- The window closed at a cumulative PnL of **{total_pnl:,.0f}** across {win_days} winning and {len(summary)-win_days} losing days.
""")
