"""
strategy.py — Backward-compatibility shim.

The strategy layer now lives in the pluggable `strategies/` package. This module
re-exports the base contract and the canonical closest-strike strategy so older
imports (e.g. `from strategy import ClosestStrikeLongStraddleStrategy, MarketState`)
keep working. New code should import from `strategies` directly.
"""

from strategies.base import MarketState, Strategy, register_strategy  # noqa: F401
from strategies.closest_strike_straddle import ClosestStrikeLongStraddleStrategy  # noqa: F401

__all__ = [
    "MarketState",
    "Strategy",
    "register_strategy",
    "ClosestStrikeLongStraddleStrategy",
]
