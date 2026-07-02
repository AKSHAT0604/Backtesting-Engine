"""
atm_open_hold_straddle.py — DUMMY strategy (ATM-at-open, buy & hold).

Picks the closest (ATM) strike at the first second a straddle is tradable, then
HOLDS that same pair for the rest of the day — no intraday rolls. The engine
still forces the end-of-day square-off.

This one is deliberately *stateful*: it remembers the strike it locked at open.
That is allowed — a strategy may keep its own internal state (an entry
reference, an indicator, a locked strike); it just must never read the
portfolio's holdings. The engine constructs a FRESH strategy instance per
(trade_date, underlier), so this per-day lock resets automatically each day.
"""

import pandas as pd

from instrument_selector import select_strike
from strategies.base import MarketState, Strategy, register_strategy


@register_strategy(
    key="atm_open_hold_straddle",
    name="ATM-at-Open Buy & Hold (dummy)",
    description=(
        "Demo strategy: lock the ATM straddle at the first tradable second and "
        "hold it until the end-of-day square-off (no intraday rolls). "
        "Illustrates a stateful plugin — near-zero turnover."
    ),
)
class AtmOpenHoldStraddleStrategy(Strategy):

    def __init__(self) -> None:
        self._locked_pair: dict[str, int] | None = None

    def get_target_positions(
        self, timestamp: pd.Timestamp, market_state: MarketState,
    ) -> dict[str, int]:
        # Once locked, keep holding the same pair for the rest of the day.
        if self._locked_pair is not None:
            return dict(self._locked_pair)

        # Not yet entered: try to lock the ATM straddle this second.
        strike = select_strike(market_state.futures_price, market_state.strikes())
        pair = market_state.pair_if_tradable(strike)
        if pair:
            self._locked_pair = dict(pair)
        return pair
