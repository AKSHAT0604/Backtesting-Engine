"""
execution_engine.py — Phase 5, Step 5.2/5.3: Order execution against PortfolioState.

Compares target holdings with current holdings, executes the diff, and records
trade records conforming to DELIVERABLES.md D3 schema.

Governed by:
    SPEC.md Rule 9       — roll = exit old legs then enter new legs
    SPEC.md Rule 10      — forced square-off at end of day
    ASSUMPTIONS.md A8    — fill at latest marked price (no slippage)
    ASSUMPTIONS.md A13   — first entry of the day is reason=ENTRY, not ROLL
    ASSUMPTIONS.md A17   — each fill is a separate trade record
    DELIVERABLES.md D3   — SELL before BUY within a roll
"""

from __future__ import annotations

import logging
from typing import NamedTuple

import pandas as pd

from portfolio_state import PortfolioState

logger = logging.getLogger(__name__)


class TradeRecord(NamedTuple):
    """One atomic fill, matching DELIVERABLES.md D3 schema."""
    trade_date: str
    timestamp: pd.Timestamp
    underlier: str
    instrument_name: str
    direction: str          # "BUY" or "SELL"
    price: float
    quantity: int            # always 1
    reason: str              # "ENTRY", "ROLL", or "SQUAREOFF"


class ExecutionEngine:
    """Compares target holdings against PortfolioState and executes changes.

    This class does NOT decide what to trade — it only executes the diff
    between current and target holdings, recording trade records.

    Parameters
    ----------
    portfolio : PortfolioState
        The mutable portfolio ledger to operate on.
    trade_date : str
        Current trading day (YYYY-MM-DD) for logging/records.
    underlier : str
        "NIFTY" or "BANKNIFTY" for logging/records.
    """

    def __init__(
        self,
        portfolio: PortfolioState,
        trade_date: str,
        underlier: str,
    ) -> None:
        self.portfolio = portfolio
        self.trade_date = trade_date
        self.underlier = underlier
        self._has_entered = False  # tracks whether first entry has occurred

    def process_target_changes(
        self,
        timestamp: pd.Timestamp,
        target_holdings: dict[str, int],
        current_market_prices: dict[str, float],
        force_squareoff: bool = False,
    ) -> list[TradeRecord]:
        """Execute the transition from current to target holdings.

        Parameters
        ----------
        timestamp : pd.Timestamp
            The second at which fills occur.
        target_holdings : dict[str, int]
            Maps instrument_name -> target quantity (0 or 1).
            Empty dict means "go flat."
        current_market_prices : dict[str, float]
            Maps instrument_name -> current marked price.
            Must contain prices for all instruments being bought or sold.
        force_squareoff : bool
            If True, overrides target_holdings to empty (forced close per Rule 10).

        Returns
        -------
        list[TradeRecord]
            All fills generated at this timestamp. SELL before BUY.
        """
        if force_squareoff:
            target_holdings = {}

        current_held = self.portfolio.held_instruments()
        target_set = {k for k, v in target_holdings.items() if v > 0}

        # If current == target, nothing to do.
        if current_held == target_set:
            return []

        # Determine reason.
        if force_squareoff:
            reason = "SQUAREOFF"
        elif not self._has_entered:
            reason = "ENTRY"
        else:
            reason = "ROLL"

        trades: list[TradeRecord] = []

        # ---- SELL old instruments first (Rule 9) --------------------------
        to_sell = sorted(current_held - target_set)
        for instr in to_sell:
            price = current_market_prices.get(instr)
            if price is None:
                logger.warning(
                    "[%s] %s @ %s: no price for %s at SELL, using entry price.",
                    self.trade_date, self.underlier, timestamp, instr,
                )
                price = self.portfolio.entry_prices.get(instr, 0.0)

            self.portfolio.close_position(instr, price)

            trades.append(TradeRecord(
                trade_date=self.trade_date,
                timestamp=timestamp,
                underlier=self.underlier,
                instrument_name=instr,
                direction="SELL",
                price=price,
                quantity=1,
                reason=reason,
            ))

        # ---- BUY new instruments ------------------------------------------
        to_buy = sorted(target_set - current_held)
        for instr in to_buy:
            price = current_market_prices.get(instr)
            if price is None:
                logger.warning(
                    "[%s] %s @ %s: no price for %s at BUY, skipping.",
                    self.trade_date, self.underlier, timestamp, instr,
                )
                continue

            self.portfolio.open_position(instr, price)

            trades.append(TradeRecord(
                trade_date=self.trade_date,
                timestamp=timestamp,
                underlier=self.underlier,
                instrument_name=instr,
                direction="BUY",
                price=price,
                quantity=1,
                reason=reason,
            ))

        # Mark that we've entered at least once.
        if to_buy and reason == "ENTRY":
            self._has_entered = True

        if trades:
            logger.debug(
                "[%s] %s @ %s: %s — %d fills.",
                self.trade_date, self.underlier, timestamp, reason, len(trades),
            )

        return trades
