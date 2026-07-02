## Edge Case Handling

Based on the logic implemented in the `ExecutionEngine` and `PortfolioState`, the backtester handles edge cases natively without manual intervention:

*   **Missing CE or PE files / missing prices at a given timestamp:**
    The engine requires valid, non-NaN prices for *both* legs of the target strike before executing an order. If either price is missing or the file does not exist, the engine skips the entry or roll and holds the current position. If no position is currently held, it remains flat until both legs become valid.

*   **Duplicate timestamps in the source data:**
    The futures data loading step standardizes and deduplicates raw ticks, rolling them up into a strict 1-second grid. The engine operates purely on this grid (`.loc[timestamp]`), ensuring it never sees duplicate timestamps. If a synthetic duplicate were passed, the engine's diffing logic (current vs target holdings) would see zero change and generate no duplicate orders or double PnL counting.

*   **Empty files:**
    Empty option files result in zero parsed strikes during the Phase 1/2 inventory and filename parsing steps. They are excluded from the `filtered_option_universe`, meaning the strategy will never target them.

*   **Days with zero strike changes:**
    If the futures price remains completely flat, the engine computes the closest strike at 09:15:00 and executes exactly one `ENTRY` (2 fills). For the rest of the day, target holdings match current holdings, generating zero `ROLL` orders. At 15:29:59, the `SQUAREOFF` rule overrides the target to flat, executing exactly one exit (2 fills).

*   **Days with extreme volatility resulting in frequent rapid strike switching:**
    The strategy acts purely on the 1-second grid. If the futures price oscillates across a strike boundary every second, the engine will aggressively generate `ROLL` orders (selling the old pair and buying the new pair). The `PortfolioState` accurately captures the realized PnL drag (whipsaw loss) from constantly entering and exiting at market prices during these rapid switches.
