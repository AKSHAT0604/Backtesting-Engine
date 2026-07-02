"""
farthest_strike_straddle.py — DUMMY strategy (deep-OTM straddle).

A deliberately different, still-valid strategy: buy CE+PE at the eligible strike
*farthest* from the futures price (a deep out-of-the-money straddle). It reuses
the exact same engine, execution, and MTM machinery — only the target-selection
rule differs — which is the whole point of the pluggable design.

Because the farthest strike is almost always a boundary of the listed range, it
rolls rarely, giving a low-churn contrast to the closest-strike strategy.
"""

import math

import pandas as pd

from strategies.base import MarketState, Strategy, register_strategy


def _select_farthest(futures_price, available_strikes):
    if futures_price is None or (isinstance(futures_price, float) and math.isnan(futures_price)):
        return None
    if not available_strikes:
        return None
    # max distance; tie-break deterministically on the lower strike (mirrors A6).
    return max(available_strikes, key=lambda k: (abs(futures_price - k), -k))


@register_strategy(
    key="farthest_strike_straddle",
    name="Farthest-Strike Long Straddle (dummy)",
    description=(
        "Demo strategy: buy CE+PE at the eligible strike FARTHEST from the "
        "futures price (deep-OTM). Low turnover; illustrates plugging in an "
        "alternative selection rule without touching the engine."
    ),
)
class FarthestStrikeLongStraddleStrategy(Strategy):

    def get_target_positions(
        self, timestamp: pd.Timestamp, market_state: MarketState,
    ) -> dict[str, int]:
        strike = _select_farthest(market_state.futures_price, market_state.strikes())
        return market_state.pair_if_tradable(strike)
