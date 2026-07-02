import pandas as pd
from pathlib import Path
import sys

# NOTE: superseded by run_strategy.py + engine/reporting.py (kept for history).
# Engine modules live in ../engine — put it on the path to reuse shared paths.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

def main():
    print("=" * 70)
    print("PHASE 7/8 — GENERATING DAILY SUMMARY")
    print("=" * 70)

    from data_paths import results_dir
    RESULTS_DIR = results_dir()
    trades_path = RESULTS_DIR / "trades.csv"
    mtm_path = RESULTS_DIR / "mtm_timeline.csv"

    if not trades_path.exists() or not mtm_path.exists():
        print("Error: trades.csv or mtm_timeline.csv not found.")
        print("Please run backtest_runner.py first.")
        sys.exit(1)

    trades = pd.read_csv(trades_path)
    mtm = pd.read_csv(mtm_path)

    dates = mtm['trade_date'].dropna().unique()
    summary_rows = []

    for date in dates:
        day_mtm = mtm[mtm['trade_date'] == date]
        last_mtm = day_mtm.iloc[-1]
        
        day_trades = trades[trades['trade_date'] == date]
        
        nifty_trades = day_trades[day_trades['underlier'] == 'NIFTY']
        bn_trades = day_trades[day_trades['underlier'] == 'BANKNIFTY']
        
        # Count roll events
        nifty_rolls = len(nifty_trades[nifty_trades['reason'] == 'ROLL']) // 4
        bn_rolls = len(bn_trades[bn_trades['reason'] == 'ROLL']) // 4
        total_rolls = nifty_rolls + bn_rolls
        
        # PnL for the day (since portfolio state resets per day)
        n_pnl = last_mtm.get('nifty_total_pnl', 0.0)
        if pd.isna(n_pnl): n_pnl = 0.0
        
        bn_pnl = last_mtm.get('banknifty_total_pnl', 0.0)
        if pd.isna(bn_pnl): bn_pnl = 0.0
        
        summary_rows.append({
            'Date': date,
            'Total PnL': n_pnl + bn_pnl,
            'Total Trades Executed (Rolls)': total_rolls,
            'NIFTY PnL': n_pnl,
            'BANKNIFTY PnL': bn_pnl,
            'NIFTY Rolls': nifty_rolls,
            'BANKNIFTY Rolls': bn_rolls
        })

    summary_df = pd.DataFrame(summary_rows)
    summary_path = RESULTS_DIR / "daily_summary.csv"
    summary_df.to_csv(summary_path, index=False)
    
    print(f"Created daily_summary.csv with {len(summary_df)} rows -> {summary_path}")
    print("\nPhase 7 & 8 data generation complete. You can now use backtest_report.ipynb.")

if __name__ == "__main__":
    main()
