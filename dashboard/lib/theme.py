"""Shared color palette and Plotly chart chrome for the analysis portal.

Colors are pulled verbatim from the project's validated data-viz palette
(fixed categorical hue order, diverging blue<->red for PnL polarity, single-hue
blue ramp for magnitude). Nothing here is eyeballed -- see the palette
reference this was derived from for the full check set.
"""

import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# Categorical slots (fixed order -- never reassigned per chart)
# ---------------------------------------------------------------------------
BLUE = "#2a78d6"      # slot 1 -- NIFTY
AQUA = "#1baf7a"       # slot 2 -- BANKNIFTY
YELLOW = "#eda100"    # slot 3
GREEN = "#008300"     # slot 4
VIOLET = "#4a3aa7"     # slot 5 -- CE leg
RED = "#e34948"       # slot 6 -- diverging negative pole
MAGENTA = "#e87ba4"   # slot 7
ORANGE = "#eb6834"     # slot 8 -- PE leg

UNDERLIER_COLOR = {"NIFTY": BLUE, "BANKNIFTY": AQUA}
LEG_COLOR = {"CE": VIOLET, "PE": ORANGE}

# Diverging pair for PnL polarity (positive/negative around zero)
POSITIVE = BLUE
NEGATIVE = RED
NEUTRAL_MID = "#f0efec"

# Sequential single-hue ramp (blue), light -> dark, for magnitude/heatmaps
SEQUENTIAL_BLUE = [
    "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef",
    "#6da7ec", "#5598e7", "#3987e5", "#2a78d6",
    "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b",
]

# Status (reserved -- state only, never a generic series)
STATUS_GOOD = "#0ca30c"
STATUS_CRITICAL = "#d03b3b"

# Chrome / ink
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"
SURFACE_WHITE = "#ffffff"

FONT_FAMILY = "system-ui, -apple-system, 'Segoe UI', sans-serif"

# ---------------------------------------------------------------------------
# Dark mode -- one lightened step of each hue's own tonal ramp (see
# .impeccable/design.json colorMeta), never a new hue. Chrome neutrals are a
# separate dark-blue-tinted scale (DESIGN.md's tinted-neutral convention).
# ---------------------------------------------------------------------------
DARK_BLUE = "#5598e7"
DARK_AQUA = "#4dc79a"
DARK_RED = "#ec7a79"
DARK_VIOLET = "#7264c0"
DARK_ORANGE = "#f18f63"

DARK_BG = "#11151c"
DARK_SURFACE = "#171c26"
DARK_MID = "#232937"
DARK_INK = "#eef1f5"
DARK_MUTED = "#8b93a1"
DARK_GRIDLINE = "#2a3040"
DARK_BASELINE = "#3c4456"


def is_dark() -> bool:
    """Whether dark mode is active for this session (sidebar toggle)."""
    return bool(st.session_state.get("dark_mode", False))


def underlier_color(name: str) -> str:
    if is_dark():
        return {"NIFTY": DARK_BLUE, "BANKNIFTY": DARK_AQUA}[name]
    return UNDERLIER_COLOR[name]


def leg_color(option_type: str) -> str:
    if is_dark():
        return {"CE": DARK_VIOLET, "PE": DARK_ORANGE}[option_type]
    return LEG_COLOR[option_type]


def ink_color() -> str:
    return DARK_INK if is_dark() else TEXT_PRIMARY


def polarity_colors() -> tuple[str, str]:
    """(positive, negative) colors for the current mode."""
    return (DARK_BLUE, DARK_RED) if is_dark() else (POSITIVE, NEGATIVE)


def surface_color() -> str:
    return DARK_SURFACE if is_dark() else SURFACE_WHITE


def muted_color() -> str:
    return DARK_MUTED if is_dark() else MUTED


def apply_base_layout(fig: go.Figure, title: str | None = None,
                       y_title: str | None = None, x_title: str | None = None,
                       show_legend: bool = True, height: int = 420) -> go.Figure:
    """Apply shared chrome: transparent surface, recessive gridlines, unified
    hover, thin baseline -- consistent across every chart in the app.

    Reads dark-mode state itself so call sites never need a `dark=` arg."""
    dark = is_dark()
    text_primary = DARK_INK if dark else TEXT_PRIMARY
    text_secondary = DARK_MUTED if dark else TEXT_SECONDARY
    muted = DARK_MUTED if dark else MUTED
    gridline = DARK_GRIDLINE if dark else GRIDLINE
    baseline = DARK_BASELINE if dark else BASELINE
    hover_bg = DARK_SURFACE if dark else SURFACE_WHITE

    fig.update_layout(
        title=dict(text=title, font=dict(size=15, color=text_primary)) if title else None,
        font=dict(family=FONT_FAMILY, color=text_secondary, size=12),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
        hoverlabel=dict(bgcolor=hover_bg, font=dict(color=text_primary, size=12),
                         bordercolor=gridline),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                     font=dict(color=text_secondary)) if show_legend else dict(visible=False),
        showlegend=show_legend,
        margin=dict(l=10, r=10, t=48 if title else 20, b=10),
        height=height,
    )
    fig.update_xaxes(
        title=dict(text=x_title, font=dict(color=muted)) if x_title else None,
        showgrid=False,
        showline=True,
        linecolor=baseline,
        tickfont=dict(color=muted, size=11),
    )
    fig.update_yaxes(
        title=dict(text=y_title, font=dict(color=muted)) if y_title else None,
        showgrid=True,
        gridcolor=gridline,
        zeroline=True,
        zerolinecolor=baseline,
        zerolinewidth=1,
        showline=False,
        tickfont=dict(color=muted, size=11),
    )
    return fig


def pnl_bar_colors(values) -> list[str]:
    """Diverging color per bar by sign -- positive/negative around zero."""
    pos, neg = polarity_colors()
    return [pos if v >= 0 else neg for v in values]
