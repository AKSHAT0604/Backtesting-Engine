"""Shared UI helpers for the portal — chiefly the strategy selector.

The selector is driven entirely by the strategy registry in the `strategies/`
package. Drop a new strategy file in that folder and it appears here
automatically; if its results aren't generated yet, the page offers a button to
run the engine for it. This is the dashboard end of the pluggable-strategy wire.
"""

from __future__ import annotations

import subprocess
import sys

import streamlit as st

from lib import data


def render_strategy_selector() -> str:
    """Render the sidebar strategy picker; return the selected strategy key.

    Persists the choice in session_state so it carries across pages.
    """
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
