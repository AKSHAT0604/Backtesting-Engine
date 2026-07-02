"""
strategies/base.py — Pluggable-strategy foundation.

This is the contract every strategy plugs into and the registry the engine and
dashboard read from. To add a new strategy you ONLY create a new file in this
folder that defines a `Strategy` subclass decorated with `@register_strategy`.
Auto-discovery (`discover_strategies`) imports every sibling module, so the new
strategy appears in the engine and the dashboard with no other wiring.

Design (SPEC.md Rule 8/9, plan Phase 4.3):
    A strategy is a PURE function of (timestamp, market_state) -> target holdings.
    It NEVER reads files, tracks its own holdings, or books trades. It only
    declares the positions it wants; the ExecutionEngine computes the diff from
    current holdings to that target. This decoupling is what makes strategies
    swappable without touching the engine.
"""

from __future__ import annotations

import importlib
import logging
import math
import pkgutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-second market context handed to a strategy
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MarketState:
    """Immutable snapshot of market context at a single evaluated second.

    Attributes
    ----------
    trade_date, underlier, timestamp : identifying context.
    grid_row : pd.Series
        Row from the wide second-grid: "futures_price" + one column per
        eligible option instrument (forward-filled prices, NaN before first tick).
    strike_lookup : dict[strike, (ce_instrument, pe_instrument)]
        Eligible strikes (both legs present) -> their instrument names.
    available_strikes : list | None
        Sorted ascending eligible strikes. Optional convenience so strategies
        need not re-sort every second; falls back to sorted(strike_lookup).
    """
    trade_date: str
    underlier: str
    timestamp: pd.Timestamp
    grid_row: Any                 # pd.Series
    strike_lookup: dict
    available_strikes: list | None = None

    # -- helpers strategies can lean on -------------------------------------
    @property
    def futures_price(self) -> float | None:
        return self.grid_row.get("futures_price")

    def strikes(self) -> list:
        if self.available_strikes is not None:
            return self.available_strikes
        return sorted(self.strike_lookup.keys())

    def price_ok(self, instrument: str) -> bool:
        """True if the instrument has a valid (non-NaN) marked price this second."""
        p = self.grid_row.get(instrument)
        return p is not None and not (isinstance(p, float) and math.isnan(p))

    def pair_if_tradable(self, strike) -> dict[str, int]:
        """Return {ce:1, pe:1} for `strike` iff both legs are priced, else {}.

        Encapsulates ASSUMPTIONS.md A5: never enter a straddle unless both the
        CE and PE at that strike have valid prices on the grid.
        """
        if strike is None or strike not in self.strike_lookup:
            return {}
        ce, pe = self.strike_lookup[strike]
        if self.price_ok(ce) and self.price_ok(pe):
            return {ce: 1, pe: 1}
        return {}


# ---------------------------------------------------------------------------
# Strategy contract
# ---------------------------------------------------------------------------

class Strategy(ABC):
    """Abstract base for all backtesting strategies.

    Subclasses implement `get_target_positions` only. They must be stateless
    with respect to holdings — the engine owns position state.
    """

    #: filled in by @register_strategy
    strategy_key: str = "unregistered"
    strategy_name: str = "Unregistered strategy"

    @abstractmethod
    def get_target_positions(
        self, timestamp: pd.Timestamp, market_state: MarketState,
    ) -> dict[str, int]:
        """Return desired holdings this second as {instrument_name: 1}.

        An empty dict means "flat" — the engine will exit any open position.
        Instruments omitted from the dict have an implicit target of 0.
        """
        ...


# ---------------------------------------------------------------------------
# Registry + auto-discovery
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StrategyInfo:
    key: str
    name: str
    description: str
    factory: type


_REGISTRY: dict[str, StrategyInfo] = {}
_DISCOVERED = False


def register_strategy(key: str, name: str | None = None, description: str = ""):
    """Class decorator that registers a strategy under a stable `key`."""
    def deco(cls: type) -> type:
        if not issubclass(cls, Strategy):
            raise TypeError(f"{cls.__name__} must subclass Strategy to be registered.")
        cls.strategy_key = key
        cls.strategy_name = name or key
        _REGISTRY[key] = StrategyInfo(key=key, name=name or key,
                                      description=description, factory=cls)
        logger.debug("Registered strategy '%s' -> %s", key, cls.__name__)
        return cls
    return deco


def discover_strategies() -> None:
    """Import every sibling module so their @register_strategy runs. Idempotent."""
    global _DISCOVERED
    if _DISCOVERED:
        return
    package = importlib.import_module(__package__)
    for mod in pkgutil.iter_modules(package.__path__):
        if mod.name in ("base", "__init__"):
            continue
        importlib.import_module(f"{__package__}.{mod.name}")
    _DISCOVERED = True


def get_registry() -> dict[str, StrategyInfo]:
    """All registered strategies, keyed by strategy key (discovery-triggered)."""
    discover_strategies()
    return dict(_REGISTRY)


def get_strategy(key: str) -> Strategy:
    """Instantiate a strategy by key."""
    discover_strategies()
    if key not in _REGISTRY:
        raise KeyError(f"Unknown strategy '{key}'. Available: {sorted(_REGISTRY)}")
    return _REGISTRY[key].factory()
