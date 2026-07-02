"""
portfolio_state.py — Phase 5, Step 5.1: Portfolio state / ledger.

Tracks current positions, entry prices, realized and unrealized PnL.
This class is strictly for state and accounting — NO order execution logic.

Governed by:
    SPEC.md Rule 6      — max position is 1 unit per instrument
    ASSUMPTIONS.md A9    — unrealized PnL = (current_price - entry_price) * qty
    ASSUMPTIONS.md A10   — no transaction costs
"""

from __future__ import annotations
import math


class PortfolioState:
    """Mutable ledger for a single (trade_date, underlier) backtest run.

    Attributes
    ----------
    current_positions : dict[str, int]
        instrument_name -> quantity (0 or 1).
    entry_prices : dict[str, float]
        instrument_name -> price at which the position was opened.
    realized_pnl : float
        Cumulative banked P&L from all closed trades.
    unrealized_pnl : float
        Floating P&L of currently open positions.
    total_mtm : float
        realized_pnl + unrealized_pnl.
    """

    def __init__(self) -> None:
        self.current_positions: dict[str, int] = {}
        self.entry_prices: dict[str, float] = {}
        self.realized_pnl: float = 0.0
        self.unrealized_pnl: float = 0.0
        self.total_mtm: float = 0.0

    # ------------------------------------------------------------------
    # Position management (called by ExecutionEngine)
    # ------------------------------------------------------------------

    def open_position(self, instrument: str, price: float) -> None:
        """Record a new long position at the given entry price."""
        self.current_positions[instrument] = 1
        self.entry_prices[instrument] = price

    def close_position(self, instrument: str, price: float) -> float:
        """Close an existing position and return the realized P&L.

        The realized P&L for this leg = (exit_price - entry_price) * 1.
        """
        entry = self.entry_prices.pop(instrument, 0.0)
        self.current_positions.pop(instrument, None)
        pnl = price - entry
        self.realized_pnl += pnl
        return pnl

    def is_flat(self) -> bool:
        """True if no instruments are currently held."""
        return not any(q > 0 for q in self.current_positions.values())

    def held_instruments(self) -> set[str]:
        """Return the set of instrument names with quantity > 0."""
        return {k for k, v in self.current_positions.items() if v > 0}

    # ------------------------------------------------------------------
    # MTM update (called every second)
    # ------------------------------------------------------------------

    def update_mtm(self, current_market_prices: dict[str, float]) -> None:
        """Recalculate unrealized PnL and total MTM from current prices.

        Parameters
        ----------
        current_market_prices : dict[str, float]
            Maps instrument_name -> current marked price.
            Only prices for held instruments are needed.
        """
        unrealized = 0.0
        for instr, qty in self.current_positions.items():
            if qty <= 0:
                continue
            entry = self.entry_prices.get(instr, 0.0)
            current = current_market_prices.get(instr)
            if current is not None and not (isinstance(current, float) and math.isnan(current)):
                unrealized += (current - entry) * qty
            # If current price is unavailable, carry last unrealized (treated as 0 change).

        self.unrealized_pnl = unrealized
        self.total_mtm = self.realized_pnl + self.unrealized_pnl

    # ------------------------------------------------------------------
    # State summary (for timeline logging)
    # ------------------------------------------------------------------

    def get_state_summary(self) -> dict:
        """Return a snapshot of the current state for logging."""
        held = self.held_instruments()
        return {
            "positions": dict(self.current_positions),
            "held_instruments": sorted(held),
            "entry_prices": dict(self.entry_prices),
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "total_mtm": self.total_mtm,
            "is_flat": self.is_flat(),
        }

    def __repr__(self) -> str:
        held = sorted(self.held_instruments())
        return (
            f"PortfolioState(held={held}, "
            f"realized={self.realized_pnl:.2f}, "
            f"unrealized={self.unrealized_pnl:.2f}, "
            f"total_mtm={self.total_mtm:.2f})"
        )
