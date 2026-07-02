"""
day_lifecycle.py — Phase 4, Step 4.2: Day-start and day-end rules.

Exports:
    DayLifecycleRules  — dataclass with callable checks
    get_day_lifecycle_rules() -> DayLifecycleRules

Governed by:
    SPEC.md Rule 10      — forced square-off at end of day
    ASSUMPTIONS.md A1    — session 09:15:00 to 15:29:59
    ASSUMPTIONS.md A13   — first entry is ENTRY not ROLL (day starts flat)
    ASSUMPTIONS.md A14   — square-off uses last marked price at 15:29:59
"""

from dataclasses import dataclass

import pandas as pd


# ---------------------------------------------------------------------------
# Session boundaries
# ---------------------------------------------------------------------------
SESSION_START_TIME = "09:15:00"
SESSION_END_TIME = "15:29:59"


# ---------------------------------------------------------------------------
# Lifecycle rules
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DayLifecycleRules:
    """Three callable checks that govern intraday lifecycle, separate from
    the core strategy decision logic.

    These are used by the execution engine to override or annotate the
    strategy's target positions at boundary conditions.
    """

    def is_session_start(self, timestamp: pd.Timestamp) -> bool:
        """True only at the very first evaluated second of the day (09:15:00).

        At session start the strategy begins flat (no prior positions).
        The first entry is logged as reason=ENTRY, not ROLL (A13).
        """
        return timestamp.strftime("%H:%M:%S") == SESSION_START_TIME

    def should_hold_position(
        self,
        current_holding_pair: tuple | None,
        target_pair: tuple | None,
    ) -> bool:
        """True if current holdings already match the target.

        Parameters
        ----------
        current_holding_pair : tuple or None
            (strike, ce_instrument_name, pe_instrument_name) or None if flat.
        target_pair : tuple or None
            Same format.  None means "target is flat."

        Returns True when both are identical — meaning no action is needed.
        """
        return current_holding_pair == target_pair

    def is_forced_squareoff(self, timestamp: pd.Timestamp) -> bool:
        """True only at the last evaluated second of the day (15:29:59).

        At this second the engine MUST override the strategy target to an
        empty dict (fully flat), regardless of what the strategy would
        normally want.  Per SPEC.md Rule 10 and A14.
        """
        return timestamp.strftime("%H:%M:%S") == SESSION_END_TIME


def get_day_lifecycle_rules() -> DayLifecycleRules:
    """Factory function returning the lifecycle rules instance."""
    return DayLifecycleRules()
