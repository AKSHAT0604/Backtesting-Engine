"""Shared UI helpers for the portal — strategy selector, view filter, theme.

The selector is driven entirely by the strategy registry in the `strategies/`
package. Drop a new strategy file in that folder and it appears here
automatically; if its results aren't generated yet, the page offers a button to
run the engine for it. This is the dashboard end of the pluggable-strategy wire.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import date

import pandas as pd
import streamlit as st

from lib import data, theme

# Committed CSS layer -- color-tinted depth and purposeful motion, not just
# hairlines. Every color here is lib/theme.py's Signal Blue (or another
# chart-scoped hue used only where its chart meaning matches) at some alpha --
# no new hues. See DESIGN.md secs 4-6 (Elevation, Components, Do's/Don'ts).
_EASE = "cubic-bezier(0.23, 1, 0.32, 1)"  # strong ease-out, no bounce/spring

_BASE_CSS = f"""
<style>
@keyframes riseIn {{
  from {{ opacity: 0; transform: translateY(8px); }}
  to   {{ opacity: 1; transform: translateY(0); }}
}}
@keyframes fadeIn {{
  from {{ opacity: 0; }}
  to   {{ opacity: 1; }}
}}

@media (prefers-reduced-motion: no-preference) {{
  .stButton > button,
  div[data-baseweb="select"] > div,
  div[data-baseweb="base-input"],
  [data-testid="stMetric"],
  [data-testid="stPlotlyChart"] {{
    transition: background-color 180ms {_EASE},
                border-color 180ms {_EASE},
                box-shadow 180ms {_EASE},
                transform 180ms {_EASE},
                color 180ms {_EASE};
  }}
  .stButton > button:active {{ transform: scale(0.97); transition-duration: 140ms; }}

  [data-testid="stHorizontalBlock"] [data-testid="stMetric"],
  [data-testid="stPlotlyChart"] {{
    animation: riseIn 320ms {_EASE} both;
  }}
  [data-testid="stHorizontalBlock"] > div:nth-child(1) [data-testid="stMetric"] {{ animation-delay: 0ms; }}
  [data-testid="stHorizontalBlock"] > div:nth-child(2) [data-testid="stMetric"] {{ animation-delay: 40ms; }}
  [data-testid="stHorizontalBlock"] > div:nth-child(3) [data-testid="stMetric"] {{ animation-delay: 80ms; }}
  [data-testid="stHorizontalBlock"] > div:nth-child(4) [data-testid="stMetric"] {{ animation-delay: 120ms; }}
  [data-testid="stHorizontalBlock"] > div:nth-child(5) [data-testid="stMetric"] {{ animation-delay: 160ms; }}
}}
@media (prefers-reduced-motion: reduce) {{
  [data-testid="stHorizontalBlock"] [data-testid="stMetric"],
  [data-testid="stPlotlyChart"] {{
    animation: fadeIn 320ms ease both;
  }}
}}

.block-container {{
    padding-top: 2rem !important;
    max-width: 1200px;
}}

/* Masthead: a committed Signal Blue rule under the title, tightened spacing
   to the caption -- the one deliberate section marker on the page. */
h1 {{
    letter-spacing: -0.01em;
    font-weight: 700 !important;
    padding-bottom: 0.75rem;
    margin-bottom: 0.5rem !important;
    border-bottom: 3px solid {theme.BLUE};
}}
h1 + div[data-testid="stCaptionContainer"] {{
    margin-top: -0.25rem;
}}
h3 {{
    letter-spacing: -0.005em;
}}

/* KPI tiles: lifted, tinted, and given real weight -- the numbers this whole
   page exists to show off. */
[data-testid="stMetric"] {{
    background-color: rgba(42, 120, 214, 0.035);
    border: 1px solid rgba(42, 120, 214, 0.12);
    border-radius: 10px;
    padding: 14px 16px;
    box-shadow: 0 1px 2px rgba(11,11,11,0.04), 0 4px 12px rgba(42,120,214,0.08);
}}
[data-testid="stMetric"]:hover {{
    border-color: rgba(42, 120, 214, 0.28);
    box-shadow: 0 2px 4px rgba(11,11,11,0.06), 0 8px 24px rgba(42,120,214,0.14);
    transform: translateY(-2px);
}}
[data-testid="stMetricLabel"] {{
    color: {theme.MUTED};
    font-size: 0.8rem;
}}
[data-testid="stMetricValue"] {{
    color: {theme.TEXT_PRIMARY};
    font-weight: 800;
    font-variant-numeric: tabular-nums;
}}
[data-testid="stMetricDeltaIcon-Up"] {{ color: {theme.BLUE} !important; }}
[data-testid="stMetricDeltaIcon-Down"] {{ color: {theme.RED} !important; }}
[data-testid="stMetricDelta"]:has([data-testid="stMetricDeltaIcon-Up"]) {{ color: {theme.BLUE} !important; }}
[data-testid="stMetricDelta"]:has([data-testid="stMetricDeltaIcon-Down"]) {{ color: {theme.RED} !important; }}

/* Chart frames: the same lifted-surface language as the KPI tiles, so
   "data lives on an elevated plane" reads as one system. */
[data-testid="stPlotlyChart"] {{
    background-color: {theme.SURFACE_WHITE};
    border-radius: 10px;
    padding: 6px;
    box-shadow: 0 1px 2px rgba(11,11,11,0.04), 0 4px 12px rgba(42,120,214,0.08);
}}
[data-testid="stPlotlyChart"]:hover {{
    box-shadow: 0 2px 4px rgba(11,11,11,0.06), 0 8px 24px rgba(42,120,214,0.14);
}}

/* Inputs: tinted at rest, glow ring on focus -- no hard outline. */
div[data-baseweb="select"] > div,
div[data-baseweb="base-input"] {{
    background-color: {theme.NEUTRAL_MID}55;
    border-color: {theme.GRIDLINE};
}}
div[data-baseweb="select"]:focus-within > div,
div[data-baseweb="base-input"]:focus-within {{
    box-shadow: 0 0 0 3px rgba(42, 120, 214, 0.15);
    border-color: {theme.BLUE};
}}

[data-testid="stSidebar"] {{
    box-shadow: 4px 0 16px rgba(11,11,11,0.04);
}}
[data-testid="stSidebar"] h3 {{
    color: {theme.BLUE};
    padding-bottom: 0.4rem;
    border-bottom: 1px solid {theme.GRIDLINE};
    margin-bottom: 0.75rem;
}}

.stButton > button {{
    border-radius: 4px;
    box-shadow: 0 1px 2px rgba(11,11,11,0.08);
}}
.stButton > button:not([kind="primary"]):hover {{
    border-color: {theme.BLUE};
    color: {theme.BLUE};
    box-shadow: 0 4px 12px rgba(42,120,214,0.20);
    transform: translateY(-1px);
}}
.stButton > button[kind="primary"]:hover {{
    /* Darker step of the Signal Blue tonal ramp (.impeccable/design.json), not a new hue. */
    background-color: #1f60a5;
    border-color: #1f60a5;
    box-shadow: 0 4px 12px rgba(42,120,214,0.28);
    transform: translateY(-1px);
}}

hr {{
    border-color: {theme.GRIDLINE} !important;
    margin: 1.75rem 0 !important;
}}
</style>
"""

# Dark-mode overrides: layered on top of _BASE_CSS with !important, so they
# win regardless of injection order. Only chrome neutrals (bg/surface/ink/
# muted/gridline) actually flip -- Signal Blue reads fine on both surfaces,
# so the accent itself is untouched (see DESIGN.md's Meaning-Tied Rule).
# Known limitation: st.dataframe renders its grid via a canvas widget that
# does not respond to CSS, so tables keep their light chrome in dark mode.
_DARK_CSS = f"""
<style>
.stApp {{ background-color: {theme.DARK_BG} !important; }}
[data-testid="stHeader"] {{ background-color: {theme.DARK_BG} !important; }}
[data-testid="stSidebar"], [data-testid="stSidebar"] > div {{
    background-color: {theme.DARK_SURFACE} !important;
}}

.stApp, .stApp p, .stApp span, .stApp label, .stApp li,
h1, h2, h3, h4,
div[data-testid="stMarkdownContainer"], div[data-testid="stMarkdownContainer"] * {{
    color: {theme.DARK_INK} !important;
}}
div[data-testid="stCaptionContainer"], div[data-testid="stCaptionContainer"] * {{
    color: {theme.DARK_MUTED} !important;
}}
h1 {{ border-bottom-color: {theme.DARK_BLUE} !important; }}
[data-testid="stSidebar"] h3 {{ color: {theme.DARK_BLUE} !important; }}

[data-testid="stMetric"] {{
    background-color: rgba(85, 152, 231, 0.09) !important;
    border-color: rgba(85, 152, 231, 0.24) !important;
}}
[data-testid="stMetricLabel"] {{ color: {theme.DARK_MUTED} !important; }}
[data-testid="stMetricValue"] {{ color: {theme.DARK_INK} !important; }}

[data-testid="stPlotlyChart"] {{ background-color: {theme.DARK_SURFACE} !important; }}

div[data-baseweb="select"] > div, div[data-baseweb="base-input"] {{
    background-color: {theme.DARK_MID} !important;
    border-color: {theme.DARK_GRIDLINE} !important;
    color: {theme.DARK_INK} !important;
}}
div[data-baseweb="popover"], ul[data-baseweb="menu"] {{
    background-color: {theme.DARK_SURFACE} !important;
}}
li[role="option"] {{ color: {theme.DARK_INK} !important; }}

hr {{ border-color: {theme.DARK_GRIDLINE} !important; }}

[data-testid="stAlert"] {{ background-color: {theme.DARK_MID} !important; }}
[data-testid="stAlert"] p {{ color: {theme.DARK_INK} !important; }}
</style>
"""


def render_strategy_selector() -> str:
    """Render the sidebar theme toggle + strategy picker; return the selected key.

    Persists choices in session_state so they carry across pages.
    """
    with st.sidebar:
        st.markdown("### Display")
        st.toggle("🌙 Dark mode", value=st.session_state.get("dark_mode", False), key="dark_mode")

    st.markdown(_BASE_CSS, unsafe_allow_html=True)
    if st.session_state.get("dark_mode", False):
        st.markdown(_DARK_CSS, unsafe_allow_html=True)

    registry = data.get_strategy_registry()
    keys = list(registry.keys())
    names = {k: registry[k].name for k in keys}

    # Default to the canonical assignment strategy if present.
    default_key = "closest_strike_straddle" if "closest_strike_straddle" in keys else keys[0]
    current = st.session_state.get("strategy_key", default_key)
    if current not in keys:
        current = default_key

    with st.sidebar:
        st.markdown("### Strategy")
        selected = st.selectbox(
            "Active strategy",
            keys,
            index=keys.index(current),
            format_func=lambda k: names[k],
            key="strategy_selectbox",
        )
        st.caption(registry[selected].description)

        available = data.strategy_results_available(selected)
        if available:
            st.success("Results loaded", icon="✅")
        else:
            st.warning("Not generated yet", icon="⚠️")

    st.session_state["strategy_key"] = selected
    return selected


def ensure_results_or_prompt(strategy_key: str) -> bool:
    """If a strategy has no generated results, show a generate button.

    Returns True if results are available (page may render), False otherwise.
    """
    if data.strategy_results_available(strategy_key):
        return True

    name = data.get_strategy_registry()[strategy_key].name
    st.warning(f"**{name}** has no backtest results yet.")
    st.markdown(
        "This strategy is registered but hasn't been run through the engine. "
        "Generate its results below (builds the 1-second grids and runs the full "
        "month — this takes a few minutes), or from a terminal run:\n\n"
        f"```\npython run_strategy.py --strategy {strategy_key}\n```"
    )
    if st.button(f"⚙️ Generate results for “{name}” now", type="primary"):
        _run_engine_for(strategy_key)
    return False


def _run_engine_for(strategy_key: str) -> None:
    """Shell out to run_strategy.py for one strategy, streaming a spinner."""
    engine_dir = data.ENGINE_DIR
    with st.spinner(f"Running the engine for {strategy_key} — this can take a few minutes…"):
        proc = subprocess.run(
            [sys.executable, "-W", "ignore", "run_strategy.py", "--strategy", strategy_key],
            cwd=str(engine_dir),
            capture_output=True,
            text=True,
        )
    if proc.returncode == 0:
        data.clear_caches()
        st.success("Done — results generated. Reloading…")
        st.rerun()
    else:
        st.error("Engine run failed. Tail of the log:")
        st.code((proc.stdout + "\n" + proc.stderr)[-3000:])


# ---------------------------------------------------------------------------
# View filter -- full month / date range / single day, shared across pages
# ---------------------------------------------------------------------------

def render_view_filter(strategy_key: str) -> dict:
    """Sidebar control: Full month / Date range / Single day.

    Returns {"mode": "full"|"range"|"day", "start": date, "end": date}.
    Persists via session_state (widget keys) so the choice carries across
    pages and reruns; Day Drilldown reads the same dict to sync its own
    date picker instead of duplicating this control.
    """
    all_dates = [date.fromisoformat(d) for d in data.get_trade_dates(strategy_key)]
    lo, hi = min(all_dates), max(all_dates)

    with st.sidebar:
        st.markdown("### View")
        mode = st.radio(
            "Time window", ["Full month", "Date range", "Single day"],
            key="view_mode",
        )

        if mode == "Date range":
            picked = st.date_input(
                "Range", value=(lo, hi), min_value=lo, max_value=hi, key="view_range",
            )
            if isinstance(picked, tuple) and len(picked) == 2:
                start, end = picked
            elif isinstance(picked, tuple) and len(picked) == 1:
                start = end = picked[0]
            else:
                start = end = picked
            if start > end:
                start, end = end, start
            result = {"mode": "range", "start": start, "end": end}

        elif mode == "Single day":
            date_strs = data.get_trade_dates(strategy_key)
            default = st.session_state.get("view_day", date_strs[0])
            if default not in date_strs:
                default = date_strs[0]
            picked_day = st.selectbox(
                "Day", date_strs, index=date_strs.index(default), key="view_day",
            )
            d = date.fromisoformat(picked_day)
            result = {"mode": "day", "start": d, "end": d}

        else:
            result = {"mode": "full", "start": lo, "end": hi}

    st.session_state["_active_view"] = result
    return result


def mask_by_view(date_like: pd.Series, view: dict) -> pd.Series:
    """Boolean mask selecting rows whose date falls inside the view window.

    Works uniformly for a datetime64 "Date" column, a "YYYY-MM-DD" string
    "trade_date" column, or a full-precision "timestamp" column -- all three
    coerce cleanly through pd.to_datetime.
    """
    if view["mode"] == "full":
        return pd.Series(True, index=date_like.index)
    d = pd.to_datetime(date_like).dt.date
    return (d >= view["start"]) & (d <= view["end"])


def render_view_caption(view: dict) -> None:
    """One-line caption naming the active window; silent when unfiltered."""
    if view["mode"] == "day":
        st.caption(f"Showing **{view['start'].strftime('%b %d, %Y')}** only.")
    elif view["mode"] == "range":
        st.caption(f"Showing **{view['start'].strftime('%b %d')} – {view['end'].strftime('%b %d, %Y')}**.")
