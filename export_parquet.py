"""
export_parquet.py — Deployment prep: mirror the heavy per-strategy result CSVs
as compressed Parquet.

The four dashboard-facing files per strategy (trades, positions_timeline,
mtm_timeline, daily_summary) are the ones that matter for page-load time and
repo size on Streamlit Community Cloud's free tier — mtm_timeline.csv alone is
50-75MB per strategy since it's one row per second for the whole month. Parquet
with Snappy compression is typically 5-10x smaller and much faster to read than
CSV, and the dashboard (dashboard/lib/data.py) prefers the .parquet file over
the .csv when both exist.

The CSVs remain the canonical DELIVERABLES.md-schema outputs — this script only
adds a Parquet copy alongside them; it never deletes or rewrites a CSV. The
Parquet copies are what get committed to the deployment repo (see .gitignore);
the CSVs stay local, regenerable at any time via `python run_strategy.py --all`.

Usage:
    python export_parquet.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "engine"))
from data_paths import results_dir  # noqa: E402

FILES = ["trades.csv", "positions_timeline.csv", "mtm_timeline.csv", "daily_summary.csv"]


def convert_dir(d: Path) -> None:
    for fname in FILES:
        csv_path = d / fname
        if not csv_path.is_file():
            continue
        parquet_path = csv_path.with_suffix(".parquet")
        df = pd.read_csv(csv_path)
        df.to_parquet(parquet_path, engine="pyarrow", compression="snappy", index=False)
        before = csv_path.stat().st_size
        after = parquet_path.stat().st_size
        print(f"  {csv_path.relative_to(RESULTS_DIR.parent)}: "
              f"{before/1e6:6.1f} MB -> {after/1e6:5.1f} MB "
              f"({after/before*100:4.1f}%)")


if __name__ == "__main__":
    RESULTS_DIR = results_dir()
    print("=" * 70)
    print("EXPORTING RESULTS TO PARQUET FOR DEPLOYMENT")
    print("=" * 70)

    print(f"\nRoot mirror ({RESULTS_DIR}):")
    convert_dir(RESULTS_DIR)

    strategies_dir = RESULTS_DIR / "strategies"
    if strategies_dir.is_dir():
        for strat_dir in sorted(strategies_dir.iterdir()):
            if strat_dir.is_dir():
                print(f"\n{strat_dir.name}:")
                convert_dir(strat_dir)

    print("\nDone. CSVs are untouched; .parquet files sit alongside them.")
