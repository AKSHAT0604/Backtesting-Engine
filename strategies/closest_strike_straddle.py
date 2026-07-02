"""
closest_strike_straddle.py — THE assignment strategy (canonical / initial).

At every second: long 1 CE + 1 PE at the strike closest to the futures price.
Roll both legs when the closest strike changes. Go flat if the closest strike's
legs are not both priced (ASSUMPTIONS.md A5). End-of-day square-off is enforced
by the engine, not here.

Implements: SPEC.md Rule 8 (closest strike), Rule 9 (roll on change),
ASSUMPTIONS.md A5 (both legs required), A6 (lower-strike tie-break via select_strike).
"""

import pandas as pd

from instrument_selector import select_strike
from strategies.base import MarketState, Strategy, register_strategy


@register_strategy(
    key="closest_strike_straddle",
    name="Closest-Strike Long Straddle",
    description=(
        "The assignment strategy: buy CE+PE at the strike nearest the futures "
        "price each second; roll both legs whenever the nearest strike changes."
    ),
)
class ClosestStrikeLongStraddleStrategy(Strategy):

    def get_target_positions(
        self, timestamp: pd.Timestamp, market_state: MarketState,
    ) -> dict[str, int]:
        strike = select_strike(market_state.futures_price, market_state.strikes())
        return market_state.pair_if_tradable(strike)
