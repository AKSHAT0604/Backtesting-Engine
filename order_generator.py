"""
order_generator.py — Phase 4, Step 4.3: Decoupled order generation.

Exports:
    Order               — named tuple for a single fill
    generate_orders(current_positions, target_positions, timestamp) -> list[Order]

Governed by:
    SPEC.md Rule 9    — roll = exit old legs then enter new legs
    ASSUMPTIONS.md A17 — each fill is a separate trade record
    DELIVERABLES.md D3 — SELL before BUY within a roll
"""

from typing import NamedTuple

import pandas as pd


class Order(NamedTuple):
    """A single atomic fill instruction.

    Fields match the trades.csv schema from DELIVERABLES.md D3.
    """
    instrument_name: str
    direction: str        # "BUY" or "SELL"
    quantity: int          # always 1
    timestamp: pd.Timestamp


def generate_orders(
    current_positions: dict[str, int],
    target_positions: dict[str, int],
    timestamp: pd.Timestamp,
) -> list[Order]:
    """Compute the orders needed to move from current to target positions.

    This function has **zero knowledge** of strike selection, futures prices,
    or any strategy-specific logic.  It only compares two position dicts.

    Parameters
    ----------
    current_positions : dict[str, int]
        Maps instrument_name -> current quantity (0 or 1).
    target_positions : dict[str, int]
        Maps instrument_name -> desired quantity (0 or 1).
    timestamp : pd.Timestamp
        The second at which these orders execute.

    Returns
    -------
    list[Order]
        SELL orders first, then BUY orders (per SPEC.md Rule 9 / DELIVERABLES.md).
        Within SELL and BUY groups, instruments are sorted alphabetically for
        deterministic output.
    """
    sell_orders: list[Order] = []
    buy_orders: list[Order] = []

    # ---- Instruments to SELL (held but not in target) ---------------------
    for instr, qty in current_positions.items():
        if qty > 0 and target_positions.get(instr, 0) == 0:
            sell_orders.append(Order(
                instrument_name=instr,
                direction="SELL",
                quantity=1,
                timestamp=timestamp,
            ))

    # ---- Instruments to BUY (in target but not held) ---------------------
    for instr, qty in target_positions.items():
        if qty > 0 and current_positions.get(instr, 0) == 0:
            buy_orders.append(Order(
                instrument_name=instr,
                direction="BUY",
                quantity=1,
                timestamp=timestamp,
            ))

    # Sort each group alphabetically for deterministic output.
    sell_orders.sort(key=lambda o: o.instrument_name)
    buy_orders.sort(key=lambda o: o.instrument_name)

    # SELL before BUY (Rule 9 — exit old legs before entering new).
    return sell_orders + buy_orders
