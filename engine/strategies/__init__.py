"""Pluggable strategy package.

Public surface:
    Strategy, MarketState        — the contract a strategy implements
    register_strategy            — decorator to plug a new strategy in
    get_registry, get_strategy   — discovery / instantiation for engine + dashboard
    discover_strategies          — force-import all strategy modules

Add a strategy by dropping a new module in this folder that defines a
`@register_strategy(...)`-decorated `Strategy` subclass. No other file changes
are needed for the engine to run it or the dashboard to list it.
"""

from strategies.base import (
    MarketState,
    Strategy,
    StrategyInfo,
    discover_strategies,
    get_registry,
    get_strategy,
    register_strategy,
)

__all__ = [
    "MarketState",
    "Strategy",
    "StrategyInfo",
    "discover_strategies",
    "get_registry",
    "get_strategy",
    "register_strategy",
]
