import numpy as np
import plotly.graph_objects as go
import streamlit as st

from lib import data, theme, ui

st.set_page_config(page_title="Roll & Turnover Analytics", page_icon="\U0001F504", layout="wide")
st.title("Roll & Turnover Analytics")

strategy_key = ui.render_strategy_selector()
if not ui.ensure_results_or_prompt(strategy_key):
    st.stop()
st.caption(f"Strategy: **{data.get_strategy_registry()[strategy_key].name}**")

view = ui.render_view_filter(strategy_key)

holding = data.holding_durations(strategy_key)
holding = holding[ui.mask_by_view(holding["trade_date"], view)]
turnover = data.turnover_by_hour(strategy_key)
turnover = turnover[ui.mask_by_view(turnover["trade_date"], view)]
rolls = data.rolls_per_day_by_underlier(strategy_key)
rolls = rolls[ui.mask_by_view(rolls["trade_date"], view)]
summary = data.load_daily_summary(strategy_key)
summary = summary[ui.mask_by_view(summary["Date"], view)]
ui.render_view_caption(view)

if summary.empty or holding.empty:
    st.warning("No trading days fall inside the selected window. Widen the range in the sidebar.")
    st.stop()

# ---------------------------------------------------------------------------
# Holding duration distribution
# ---------------------------------------------------------------------------
st.subheader("Holding-duration distribution")
st.caption("How long each CE+PE pair stayed on before the strike rolled or the day closed.")

clip_pct = st.slider("Clip outliers above percentile", 80, 100, 98)
fig = go.Figure()
for underlier in theme.UNDERLIER_COLOR:
    d = holding.loc[holding["underlier"] == underlier, "duration_sec"]
    if d.empty:
        continue
    cap = np.percentile(d, clip_pct)
    fig.add_trace(go.Histogram(
        x=d[d <= cap], name=underlier, marker_color=theme.underlier_color(underlier), opacity=0.65, nbinsx=60,
        hovertemplate="Duration: %{x:.0f}s<br>Count: %{y}<extra></extra>",
    ))
fig.update_layout(barmode="overlay")
theme.apply_base_layout(fig, x_title="Holding duration (seconds)", y_title="Count", height=380)
st.plotly_chart(fig, width='stretch')

m1, m2 = st.columns(2)
for col, underlier in zip((m1, m2), ("NIFTY", "BANKNIFTY")):
    d = holding.loc[holding["underlier"] == underlier, "duration_sec"]
    col.metric(f"{underlier} median hold", f"{d.median():.0f}s" if not d.empty else "n/a")

st.divider()

# ---------------------------------------------------------------------------
# Turnover heatmap — day x hour
# ---------------------------------------------------------------------------
st.subheader("Trade activity heatmap — date × hour")
pivot = turnover.pivot(index="trade_date", columns="hour", values="trade_count").fillna(0)
pivot = pivot.sort_index()

heat = go.Figure(data=go.Heatmap(
    z=pivot.values, x=[f"{h:02d}:00" for h in pivot.columns], y=pivot.index,
    colorscale=[[i / (len(theme.SEQUENTIAL_BLUE) - 1), c] for i, c in enumerate(theme.SEQUENTIAL_BLUE)],
    hovertemplate="%{y} %{x}<br>Trades: %{z}<extra></extra>",
    colorbar=dict(title="Trades", outlinewidth=0),
))
theme.apply_base_layout(heat, y_title=None, x_title=None, show_legend=False, height=520)
heat.update_yaxes(autorange="reversed")
st.plotly_chart(heat, width='stretch')

st.divider()

# ---------------------------------------------------------------------------
# Rolls vs day PnL — does turnover correlate with outcome?
# ---------------------------------------------------------------------------
st.subheader("Turnover vs. day PnL")
scatter = go.Figure()
scatter.add_trace(go.Scatter(
    x=summary["Total Trades Executed (Rolls)"], y=summary["Total PnL"],
    mode="markers",
    marker=dict(size=10, color=theme.pnl_bar_colors(summary["Total PnL"]),
                line=dict(width=1, color=theme.surface_color())),
    text=summary["Date"].dt.strftime("%Y-%m-%d"),
    hovertemplate="%{text}<br>Rolls: %{x}<br>PnL: %{y:,.0f}<extra></extra>",
))
theme.apply_base_layout(scatter, x_title="Total rolls that day", y_title="Day PnL", show_legend=False, height=380)
st.plotly_chart(scatter, width='stretch')

corr = summary["Total Trades Executed (Rolls)"].corr(summary["Total PnL"])
st.caption(f"Correlation between daily roll count and daily PnL: **{corr:.2f}** "
           f"({'no meaningful relationship' if abs(corr) < 0.2 else 'weak relationship' if abs(corr) < 0.5 else 'notable relationship'}).")

st.divider()

# ---------------------------------------------------------------------------
# Rolls per day by underlier (full table + chart)
# ---------------------------------------------------------------------------
st.subheader("Rolls per day by underlier")
roll_pivot = rolls.pivot(index="trade_date", columns="underlier", values="rolls").fillna(0).astype(int)
st.dataframe(roll_pivot, width='stretch')
