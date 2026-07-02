"""Shared color palette and Plotly chart chrome for the analysis portal.

Colors are pulled verbatim from the project's validated data-viz palette
(fixed categorical hue order, diverging blue<->red for PnL polarity, single-hue
blue ramp for magnitude). Nothing here is eyeballed -- see the palette
reference this was derived from for the full check set.
"""

import plotly.graph_objects as go

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

FONT_FAMILY = "system-ui, -apple-system, 'Segoe UI', sans-serif"


def apply_base_layout(fig: go.Figure, title: str | None = None,
                       y_title: str | None = None, x_title: str | None = None,
                       show_legend: bool = True, height: int = 420) -> go.Figure:
    """Apply shared chrome: transparent surface, recessive gridlines, unified
    hover, thin baseline -- consistent across every chart in the app."""
    fig.update_layout(
        title=dict(text=title, font=dict(size=15, color=TEXT_PRIMARY)) if title else None,
        font=dict(family=FONT_FAMILY, color=TEXT_SECONDARY, size=12),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
        hoverlabel=dict(bgcolor="#ffffff", font=dict(color=TEXT_PRIMARY, size=12),
                         bordercolor=GRIDLINE),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                     font=dict(color=TEXT_SECONDARY)) if show_legend else dict(visible=False),
        showlegend=show_legend,
        margin=dict(l=10, r=10, t=48 if title else 20, b=10),
        height=height,
    )
    fig.update_xaxes(
        title=dict(text=x_title, font=dict(color=MUTED)) if x_title else None,
        showgrid=False,
        showline=True,
        linecolor=BASELINE,
        tickfont=dict(color=MUTED, size=11),
    )
    fig.update_yaxes(
        title=dict(text=y_title, font=dict(color=MUTED)) if y_title else None,
        showgrid=True,
        gridcolor=GRIDLINE,
        zeroline=True,
        zerolinecolor=BASELINE,
        zerolinewidth=1,
        showline=False,
        tickfont=dict(color=MUTED, size=11),
    )
    return fig


def pnl_bar_colors(values) -> list[str]:
    """Diverging color per bar by sign -- positive/negative around zero."""
    return [POSITIVE if v >= 0 else NEGATIVE for v in values]
