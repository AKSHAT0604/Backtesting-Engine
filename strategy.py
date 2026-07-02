"""
strategy.py — Phase 4, Step 4.1: Target-position logic.

Exports:
    Strategy          — abstract base class
    MarketState       — lightweight container for per-second market context
    ClosestStrikeLongStraddleStrategy — concrete strategy implementation

Governed by:
    SPEC.md Rule 6  — max position size is 1 unit per instrument
    SPEC.md Rule 8  — closest strike to futures price
    SPEC.md Rule 9  — roll when closest strike changes
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import pandas as pd

from instrument_selector import get_target_pair


# ---------------------------------------------------------------------------
# Market state container
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MarketState:
    """Immutable snapshot of market context at a single evaluated second.

    Attributes
    ----------
    trade_date : str
        Trading day (YYYY-MM-DD).
    underlier : str
        "NIFTY" or "BANKNIFTY".
    timestamp : pd.Timestamp
        The evaluated second.
    grid_row : pd.Series
        The row from the wide second-grid DataFrame at this timestamp.
        Contains futures_price and all option instrument prices.
    strike_lookup : dict
        Maps eligible strike -> (ce_instrument_name, pe_instrument_name).
    """
    trade_date: str
    underlier: str
    timestamp: pd.Timestamp
    grid_row: Any          # pd.Series — typed as Any to avoid import issues
    strike_lookup: dict


# ---------------------------------------------------------------------------
# Abstract strategy base
# ---------------------------------------------------------------------------

class Strategy(ABC):
    """Abstract base class for all backtesting strategies.

    A strategy is a **pure function** of (timestamp, market_state).
    It must NOT:
      - Read raw CSV files.
      - Track current holdings or internal mutable position state.
      - Generate orders or booking records.

    It returns the desired target position as a dict.
    """

    @abstractmethod
    def get_target_positions(
        self,
        timestamp: pd.Timestamp,
        market_state: MarketState,
    ) -> dict[str, int]:
        """Return target positions at this second.

        Returns
        -------
        dict[str, int]
            Maps instrument_name -> target quantity (0 or 1).
            Instruments not present in the dict have an implicit target of 0.
            An empty dict means "fully flat — no positions desired."
        """
        ...


# ---------------------------------------------------------------------------
# Concrete implementation
# ---------------------------------------------------------------------------

class ClosestStrikeLongStraddleStrategy(Strategy):
    """Long straddle at the closest strike to the current futures price.

    At every evaluated second the desired position is:
      - 1 unit of the closest-strike CE
      - 1 unit of the closest-strike PE
      - 0 in everything else

    If the closest strike cannot be determined (NaN futures price, no eligible
    strikes, or a leg price is unavailable), the target is fully flat (empty
    dict), meaning the engine should close any existing positions.
    """

    def get_target_positions(
        self,
        timestamp: pd.Timestamp,
        market_state: MarketState,
    ) -> dict[str, int]:
        # Build a mini second_grid_df (single-row) that get_target_pair expects.
        # get_target_pair indexes into second_grid_df using .at[timestamp, col],
        # so we wrap the grid_row back into a 1-row DataFrame.
        mini_grid = market_state.grid_row.to_frame().T
        mini_grid.index = [timestamp]

        strike, ce_instr, pe_instr = get_target_pair(
            trade_date=market_state.trade_date,
            underlier=market_state.underlier,
            timestamp=timestamp,
            second_grid_df=mini_grid,
            strike_lookup=market_state.strike_lookup,
        )

        if strike is None:
            return {}

        return {ce_instr: 1, pe_instr: 1}
