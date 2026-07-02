"""
data_paths.py — Single source of truth for locating the raw dataset.

The `Data/allData/` dataset may sit either inside this engine directory
(`Backtesting-Engine/Data/allData/`) or one level up at the repository root
(`FinTechProject/Data/allData/`). Every entry point resolves it through
`resolve_data_root` so the whole pipeline runs from a clean checkout regardless
of which of those two standard locations the data was unpacked into.
"""

from pathlib import Path


def resolve_data_root(script_dir=None) -> Path:
    """Return the Data/allData directory, checking the engine dir then repo root.

    Parameters
    ----------
    script_dir : str | Path | None
        Directory to anchor the search from (usually the calling script's
        folder). Defaults to this module's directory.
    """
    here = Path(script_dir).resolve() if script_dir else Path(__file__).resolve().parent
    for candidate in (here / "Data" / "allData", here.parent / "Data" / "allData"):
        if candidate.is_dir():
            return candidate
    # Fall back to the engine-local path so any error surfaces clearly downstream.
    return here / "Data" / "allData"
