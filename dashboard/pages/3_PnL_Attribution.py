import plotly.graph_objects as go
import streamlit as st

from lib import data, theme, ui

st.set_page_config(page_title="PnL Attribution", page_icon="\U0001F9EE", layout="wide")
st.title("PnL Attribution")

strategy_key = ui.render_strategy_selector()
if not ui.ensure_results_or_prompt(strategy_key):
    st.stop()
st.caption(f"Strategy: **{data.get_strategy_registry()[strategy_key].name}**")

cum = data.get_full_cumulative_mtm(strategy_key)
legs = data.leg_pnl_summary(strategy_key)
summary = data.load_daily_summary(strategy_key)

# ---------------------------------------------------------------------------
# NIFTY vs BANKNIFTY cumulative
# ---------------------------------------------------------------------------
st.subheader("Cumulative PnL — NIFTY vs BANKNIFTY")
fig = go.Figure()
fig.add_trace(go.Scatter(x=cum["timestamp"], y=cum["nifty_cumulative"], name="NIFTY",
                          mode="lines", line=dict(color=theme.UNDERLIER_COLOR["NIFTY"], width=2),
                          hovertemplate="%{x|%d %b %H:%M}<br>NIFTY: %{y:,.0f}<extra></extra>"))
fig.add_trace(go.Scatter(x=cum["timestamp"], y=cum["banknifty_cumulative"], name="BANKNIFTY",
                          mode="lines", line=dict(color=theme.UNDERLIER_COLOR["BANKNIFTY"], width=2),
                          hovertemplate="%{x|%d %b %H:%M}<br>BANKNIFTY: %{y:,.0f}<extra></extra>"))
theme.apply_base_layout(fig, y_title="PnL", height=380)
st.plotly_chart(fig, width='stretch')

st.divider()

# ---------------------------------------------------------------------------
# Drawdown curve
# ---------------------------------------------------------------------------
st.subheader("Drawdown (from running peak)")
running_peak = cum["cumulative_pnl"].cummax()
drawdown = cum["cumulative_pnl"] - running_peak
dd_fig = go.Figure()
dd_fig.add_trace(go.Scatter(x=cum["timestamp"], y=drawdown, mode="lines",
                             line=dict(color=theme.NEGATIVE, width=2),
                             fill="tozeroy", fillcolor="rgba(227,73,72,0.12)",
                             hovertemplate="%{x|%d %b %H:%M}<br>Drawdown: %{y:,.0f}<extra></extra>"))
theme.apply_base_layout(dd_fig, y_title="Drawdown", show_legend=False, height=320)
st.plotly_chart(dd_fig, width='stretch')
st.caption(f"Maximum drawdown over the month: **{drawdown.min():,.0f}**.")

st.divider()

# ---------------------------------------------------------------------------
# CE vs PE leg attribution
# ---------------------------------------------------------------------------
st.subheader("CE vs PE leg attribution")
by_leg = legs.groupby("option_type")["realized_pnl"].sum().reindex(["CE", "PE"]).fillna(0)
by_leg_underlier = legs.groupby(["underlier", "option_type"])["realized_pnl"].sum().unstack("option_type").fillna(0)

lc1, lc2 = st.columns(2)
with lc1:
    pie = go.Figure(data=go.Pie(
        labels=by_leg.index, values=by_leg.values,
        marker=dict(colors=[theme.LEG_COLOR[t] for t in by_leg.index]),
        hovertemplate="%{label}: %{value:,.0f}<extra></extra>",
        hole=0.45,
    ))
    theme.apply_base_layout(pie, title="Realized PnL share by leg type", height=340)
    st.plotly_chart(pie, width='stretch')
with lc2:
    bar = go.Figure()
    for leg_type, color in theme.LEG_COLOR.items():
        if leg_type in by_leg_underlier.columns:
            bar.add_trace(go.Bar(x=by_leg_underlier.index, y=by_leg_underlier[leg_type],
                                  name=leg_type, marker_color=color,
                                  hovertemplate="%{x} " + leg_type + ": %{y:,.0f}<extra></extra>"))
    bar.update_layout(barmode="group")
    theme.apply_base_layout(bar, title="Realized PnL by underlier and leg", y_title="PnL", height=340)
    st.plotly_chart(bar, width='stretch')

st.divider()

# ---------------------------------------------------------------------------
# Best / worst days
# ---------------------------------------------------------------------------
st.subheader("Best and worst days")
b1, b2 = st.columns(2)
with b1:
    st.markdown("**Top 5 days**")
    st.dataframe(summary.nlargest(5, "Total PnL")[["Date", "Total PnL", "NIFTY PnL", "BANKNIFTY PnL",
                                                     "Total Trades Executed (Rolls)"]],
                 hide_index=True, width='stretch')
with b2:
    st.markdown("**Bottom 5 days**")
    st.dataframe(summary.nsmallest(5, "Total PnL")[["Date", "Total PnL", "NIFTY PnL", "BANKNIFTY PnL",
                                                      "Total Trades Executed (Rolls)"]],
                 hide_index=True, width='stretch')
