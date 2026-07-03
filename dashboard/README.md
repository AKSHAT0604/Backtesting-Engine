# Analysis Portal

Interactive Streamlit + Plotly portal on top of the backtest outputs in
`../results/`. Built as the Phase 10.5 presentation layer on top of the
already-validated base engine — it doesn't recompute anything, it just
reads `trades.csv`, `positions_timeline.csv`, `mtm_timeline.csv` and
`daily_summary.csv`, plus (optionally) the raw `Data/allData/` ticks for
day-level drilldowns.

## Pages

- **Home** — month KPIs, full-resolution cumulative PnL, daily PnL bar chart
  (click a bar to open that day in the drilldown), rolls/day by underlier,
  auto-generated findings.
- **Day Drilldown** — pick any date: intraday MTM (NIFTY/BANKNIFTY/combined)
  with roll markers, futures price vs. selected strike overlay, stitched
  held-CE/PE price series across rolls, and the raw positions/trades tables
  for that day.
- **Roll & Turnover Analytics** — holding-duration distribution, a
  date×hour trade-activity heatmap, turnover-vs-PnL scatter, rolls/day table.
- **PnL Attribution** — NIFTY vs BANKNIFTY cumulative comparison, drawdown
  curve, CE vs PE realized-PnL split, best/worst days.
- **Risk Metrics** — Sharpe/Sortino/Calmar, win rate, profit factor, max
  drawdown duration, rolling Sharpe, and transaction-cost sensitivity
  (gross vs. net PnL at 0/1/2/5/10/20 bps per trade).

Every page (except Home's month-level KPIs, which respond to the same
control) reads a sidebar **View** filter — Full month / Date range / Single
day — that scopes all data on the page to that window. A sidebar **Dark
mode** toggle switches the whole app and every chart's palette; native
`st.dataframe` tables keep their light chrome regardless (Streamlit renders
that grid via a canvas widget that doesn't respond to CSS).

## Run locally

```bash
pip install -r requirements.txt
streamlit run Home.py
```

Needs `../results/*.csv` to exist (run the base backtest first). The
futures-overlay and held-leg-price charts also need the raw dataset at
`../../Data/allData/` — if that folder isn't present, those two charts show
a warning and skip gracefully; everything else works from `results/` alone.

## Deploy (Streamlit Community Cloud)

1. Push this repo to GitHub (raw tick data isn't needed in the repo if you
   accept the two optional charts being unavailable — otherwise include it
   or mount it separately).
2. On https://share.streamlit.io, point a new app at this repo with
   **main file path** `Backtesting-Engine/dashboard/Home.py`.
3. It picks up `requirements.txt` automatically.
