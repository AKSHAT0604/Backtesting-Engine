import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import data, theme, ui

st.set_page_config(page_title="Day Drilldown", page_icon="\U0001F50E", layout="wide")
st.title("Day Drilldown")

strategy_key = ui.render_strategy_selector()
if not ui.ensure_results_or_prompt(strategy_key):
    st.stop()
st.caption(f"Strategy: **{data.get_strategy_registry()[strategy_key].name}**")

all_dates = data.get_trade_dates(strategy_key)
default_date = st.session_state.get("selected_date", all_dates[0])
if default_date not in all_dates:
    default_date = all_dates[0]

col_a, col_b = st.columns([2, 1])
with col_a:
    selected_date = st.selectbox("Trade date", all_dates, index=all_dates.index(default_date))
with col_b:
    underlier_view = st.radio("Underlier", ["Combined", "NIFTY", "BANKNIFTY"], horizontal=True)
st.session_state["selected_date"] = selected_date

mtm = data.load_mtm(strategy_key)
positions = data.load_positions(strategy_key)
trades = data.load_trades(strategy_key)

day_mtm = mtm[mtm["trade_date"] == selected_date].sort_values("timestamp")
day_positions = positions[positions["trade_date"] == selected_date].sort_values("timestamp")
day_trades = trades[trades["trade_date"] == selected_date].sort_values("timestamp")

if underlier_view != "Combined":
    day_positions = day_positions[day_positions["underlier"] == underlier_view]
    day_trades = day_trades[day_trades["underlier"] == underlier_view]

# ---------------------------------------------------------------------------
# KPI row for the day
# ---------------------------------------------------------------------------
day_summary_row = data.load_daily_summary(strategy_key)
day_summary_row = day_summary_row[day_summary_row["Date"].dt.strftime("%Y-%m-%d") == selected_date].iloc[0]
n_rolls = len(day_positions[day_positions["trigger"] == "ROLL"])
n_trades = len(day_trades)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Day total PnL", f"{day_summary_row['Total PnL']:+.2f}")
c2.metric("NIFTY PnL", f"{day_summary_row['NIFTY PnL']:+.2f}")
c3.metric("BANKNIFTY PnL", f"{day_summary_row['BANKNIFTY PnL']:+.2f}")
c4.metric("Rolls / trades shown", f"{n_rolls} / {n_trades}")

st.divider()

# ---------------------------------------------------------------------------
# Intraday MTM
# ---------------------------------------------------------------------------
st.subheader(f"Intraday mark-to-market — {selected_date}")

fig = go.Figure()
if underlier_view in ("Combined", "NIFTY"):
    fig.add_trace(go.Scatter(x=day_mtm["timestamp"], y=day_mtm["nifty_total_pnl"],
                              name="NIFTY", mode="lines",
                              line=dict(color=theme.UNDERLIER_COLOR["NIFTY"], width=2),
                              hovertemplate="%{x|%H:%M:%S}<br>NIFTY: %{y:,.1f}<extra></extra>"))
if underlier_view in ("Combined", "BANKNIFTY"):
    fig.add_trace(go.Scatter(x=day_mtm["timestamp"], y=day_mtm["banknifty_total_pnl"],
                              name="BANKNIFTY", mode="lines",
                              line=dict(color=theme.UNDERLIER_COLOR["BANKNIFTY"], width=2),
                              hovertemplate="%{x|%H:%M:%S}<br>BANKNIFTY: %{y:,.1f}<extra></extra>"))
if underlier_view == "Combined":
    fig.add_trace(go.Scatter(x=day_mtm["timestamp"], y=day_mtm["combined_total_pnl"],
                              name="Combined", mode="lines",
                              line=dict(color=theme.TEXT_PRIMARY, width=2, dash="dot"),
                              hovertemplate="%{x|%H:%M:%S}<br>Combined: %{y:,.1f}<extra></extra>"))

roll_times = day_positions.loc[day_positions["trigger"] == "ROLL", "timestamp"]
if 0 < len(roll_times) <= 60:
    for t in roll_times:
        fig.add_vline(x=t, line_width=1, line_dash="dot", line_color=theme.MUTED, opacity=0.35)
elif len(roll_times) > 60:
    st.caption(f"{len(roll_times)} rolls today — too many to mark individually on the chart.")

theme.apply_base_layout(fig, y_title="PnL", height=420)
st.plotly_chart(fig, width='stretch')

st.divider()

# ---------------------------------------------------------------------------
# Futures price vs. selected strike
# ---------------------------------------------------------------------------
st.subheader("Futures price vs. selected strike")

if not data.raw_data_available():
    st.warning("Raw tick data (Data/allData) not found — this overlay needs the source dataset.")
else:
    strike_underliers = ["NIFTY", "BANKNIFTY"] if underlier_view == "Combined" else [underlier_view]
    for u in strike_underliers:
        fut = data.load_day_futures(selected_date, u)
        u_positions = positions[(positions["trade_date"] == selected_date) & (positions["underlier"] == u)]
        if fut.empty or u_positions.empty:
            st.caption(f"No data for {u} on {selected_date}.")
            continue

        strike_steps = u_positions[["timestamp", "strike"]].dropna()
        strike_series = pd.merge_asof(fut[["timestamp"]], strike_steps, on="timestamp", direction="backward")

        f2 = go.Figure()
        f2.add_trace(go.Scatter(x=fut["timestamp"], y=fut["price"], name="Futures price",
                                 mode="lines", line=dict(color=theme.UNDERLIER_COLOR[u], width=2),
                                 hovertemplate="%{x|%H:%M:%S}<br>Futures: %{y:,.1f}<extra></extra>"))
        f2.add_trace(go.Scatter(x=strike_series["timestamp"], y=strike_series["strike"], name="Selected strike",
                                 mode="lines", line=dict(color=theme.TEXT_PRIMARY, width=1.5, dash="dot", shape="hv"),
                                 hovertemplate="%{x|%H:%M:%S}<br>Strike: %{y:,.0f}<extra></extra>"))
        theme.apply_base_layout(f2, title=u, y_title="Price", height=340)
        st.plotly_chart(f2, width='stretch')

st.divider()

# ---------------------------------------------------------------------------
# Held CE / PE leg prices (optional — costs raw I/O per distinct instrument)
# ---------------------------------------------------------------------------
st.subheader("Held CE / PE leg price (stitched across rolls)")
load_legs = st.checkbox(
    "Load held-option leg prices for this day",
    value=(n_rolls <= 40),
    help="Reads the raw tick file for every distinct instrument held that day. "
         "Unchecked by default on high-turnover days to avoid a slow first load.",
)

if load_legs and data.raw_data_available():
    leg_underliers = ["NIFTY", "BANKNIFTY"] if underlier_view == "Combined" else [underlier_view]
    for u in leg_underliers:
        u_positions = positions[(positions["trade_date"] == selected_date)
                                 & (positions["underlier"] == u)
                                 & (positions["state"] == "HOLDING")].sort_values("timestamp")
        if u_positions.empty:
            continue
        u_positions = u_positions.copy()
        u_positions["next_timestamp"] = u_positions["timestamp"].shift(-1)

        ce_parts, pe_parts = [], []
        with st.spinner(f"Loading {u} leg prices..."):
            for _, row in u_positions.iterrows():
                end = row["next_timestamp"] if pd.notna(row["next_timestamp"]) else pd.Timestamp.max
                ce_px = data.load_day_instrument(selected_date, row["ce_instrument"])
                pe_px = data.load_day_instrument(selected_date, row["pe_instrument"])
                ce_parts.append(ce_px[(ce_px["timestamp"] >= row["timestamp"]) & (ce_px["timestamp"] < end)])
                pe_parts.append(pe_px[(pe_px["timestamp"] >= row["timestamp"]) & (pe_px["timestamp"] < end)])

        ce_all = pd.concat(ce_parts, ignore_index=True) if ce_parts else pd.DataFrame()
        pe_all = pd.concat(pe_parts, ignore_index=True) if pe_parts else pd.DataFrame()

        f3 = go.Figure()
        if not ce_all.empty:
            f3.add_trace(go.Scatter(x=ce_all["timestamp"], y=ce_all["price"], name="CE (held)",
                                     mode="lines", line=dict(color=theme.LEG_COLOR["CE"], width=1.5),
                                     hovertemplate="%{x|%H:%M:%S}<br>CE: %{y:,.2f}<extra></extra>"))
        if not pe_all.empty:
            f3.add_trace(go.Scatter(x=pe_all["timestamp"], y=pe_all["price"], name="PE (held)",
                                     mode="lines", line=dict(color=theme.LEG_COLOR["PE"], width=1.5),
                                     hovertemplate="%{x|%H:%M:%S}<br>PE: %{y:,.2f}<extra></extra>"))
        theme.apply_base_layout(f3, title=u, y_title="Option price", height=340)
        st.plotly_chart(f3, width='stretch')
elif load_legs:
    st.warning("Raw tick data (Data/allData) not found.")

st.divider()

# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------
tab1, tab2 = st.tabs(["Positions timeline", "Trades"])
with tab1:
    st.dataframe(day_positions.drop(columns=["trade_date"]), width='stretch', hide_index=True)
with tab2:
    st.dataframe(day_trades.drop(columns=["trade_date"]), width='stretch', hide_index=True)
