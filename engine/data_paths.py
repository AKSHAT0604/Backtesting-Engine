"""
data_paths.py — Single source of truth for all project paths.

This module lives in `Backtesting-Engine/engine/`, so it can locate every other
directory relative to its own known position, no matter where the calling script
physically sits (root runner, `data_cleaning/`, `tests/`, `dashboard/`, …). Every
script imports its paths from here instead of computing them from its own
`__file__`, which is what lets the code be reorganised into folders without
breaking.

Key paths:
    ENGINE_CODE_DIR   .../Backtesting-Engine/engine   (the importable modules)
    ENGINE_ROOT       .../Backtesting-Engine          (holds results/, dashboard/, run_strategy.py)
    REPO_ROOT         .../FinTechProject               (may hold Data/, SPEC.md, ASSUMPTIONS.md)

The raw dataset (`Data/allData/`) may sit under ENGINE_ROOT or REPO_ROOT; both
are checked.
"""

from pathlib import Path

_THIS = Path(__file__).resolve()
ENGINE_CODE_DIR = _THIS.parent            # .../Backtesting-Engine/engine
ENGINE_ROOT = ENGINE_CODE_DIR.parent      # .../Backtesting-Engine
REPO_ROOT = ENGINE_ROOT.parent            # .../FinTechProject


def resolve_data_root(script_dir=None) -> Path:
    """Return the Data/allData directory, checking the engine root then repo root.

    `script_dir` is accepted for backward compatibility but ignored — resolution
    is anchored on this module's known location, which is robust to the caller's
    working directory or folder.
    """
    for candidate in (ENGINE_ROOT / "Data" / "allData", REPO_ROOT / "Data" / "allData"):
        if candidate.is_dir():
            return candidate
    # Fall back to the engine-root path so any error surfaces clearly downstream.
    return ENGINE_ROOT / "Data" / "allData"


def results_dir() -> Path:
    """The canonical results directory (Backtesting-Engine/results), created if absent."""
    d = ENGINE_ROOT / "results"
    d.mkdir(parents=True, exist_ok=True)
    return d


def engine_code_dir() -> Path:
    """The folder holding the importable engine modules (for sys.path setup)."""
    return ENGINE_CODE_DIR
