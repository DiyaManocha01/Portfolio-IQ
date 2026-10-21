#!/usr/bin/env python3
"""Run the Phase 13 ML-strategy backtest and write reproducible outputs.

Unlike scripts/fetch_nifty100.py and scripts/fetch_news_rss.py, this
script needs NO network access -- it runs entirely against whatever is
already in the local database (seeded synthetic data by default, or a
real NIFTY 100 cache if you've populated one via fetch_nifty100.py and
retrained). It CAN be run in a network-restricted sandbox.

Usage:
    cd backend
    source venv/bin/activate
    python scripts/run_backtest.py

Writes to backend/app/data/backtests/ (gitignored, regeneratable):
    - backtest_summary.csv      one row per strategy (ml_strategy/buy_and_hold/momentum)
    - ablation_results.csv      one row per feature-group-removed scenario
    - dsr_bootstrap_summary.json  Deflated Sharpe Ratio + paired bootstrap results
    - equity_curves.png         cumulative equity curves, all three strategies

The numbers this produces for the CURRENT (synthetic, DEV_SAMPLE) seeded
data are transcribed honestly into docs/methodology.md Section 10 -- they
say the methodology runs correctly, not that this is a profitable
strategy; see docs/limitations.md for why a synthetic random walk has no
real exploitable signal by construction.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database.session import SessionLocal
from app.ml import backtest, train

OUT_DIR = Path(__file__).resolve().parent.parent / "app" / "data" / "backtests"


def main() -> None:
    db = SessionLocal()
    metadata = train.load_metadata()
    if metadata is None:
        raise SystemExit("No trained model found. Run `python -m app.data.seed` first (it trains the model).")
    selected_model = metadata["selected_model"]
    print(f"Backtesting selected model type: {selected_model}")

    result = backtest.run_backtest(db, selected_model)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    summary_path = OUT_DIR / "backtest_summary.csv"
    with summary_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(result["strategy_summaries"][0].keys()))
        writer.writeheader()
        writer.writerows(result["strategy_summaries"])
    print(f"Wrote {summary_path}")

    ablation_path = OUT_DIR / "ablation_results.csv"
    with ablation_path.open("w", newline="") as f:
        fieldnames = ["feature_group_removed", "mean_val_auc", "delta_vs_full", "remaining_features"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in result["ablation"]:
            writer.writerow({**row, "remaining_features": ",".join(row["remaining_features"])})
    print(f"Wrote {ablation_path}")

    dsr_path = OUT_DIR / "dsr_bootstrap_summary.json"
    dsr_path.write_text(
        json.dumps(
            {
                "selected_model": result["selected_model"],
                "positive_threshold": result["positive_threshold"],
                "trial_sharpes_per_period": result["trial_sharpes_per_period"],
                "deflated_sharpe_ratio": result["deflated_sharpe_ratio"],
                "paired_bootstrap_vs_buy_and_hold": result["paired_bootstrap_vs_buy_and_hold"],
            },
            indent=2,
        )
    )
    print(f"Wrote {dsr_path}")

    _save_equity_curve_plot(db, selected_model, OUT_DIR / "equity_curves.png")

    print("\n--- Strategy summary ---")
    for row in result["strategy_summaries"]:
        print(
            f"  {row['strategy']:15s} ann.return={row['annualized_return']:+.4f}  "
            f"ann.vol={row['annualized_volatility']:.4f}  sharpe={row['sharpe_ratio']:+.3f}  "
            f"max_dd={row['max_drawdown']:.4f}"
        )
    dsr = result["deflated_sharpe_ratio"]
    print(f"\nDeflated Sharpe Ratio: {dsr['dsr']:.4f} (N={dsr['n_trials']} trials, SR0={dsr['sr0_per_period']:.5f})")
    bootstrap = result["paired_bootstrap_vs_buy_and_hold"]
    print(
        f"Paired bootstrap vs buy-and-hold: mean Sharpe diff = {bootstrap['mean_sharpe_diff_per_period']:+.5f} "
        f"(95% CI [{bootstrap['ci_95_low']:+.5f}, {bootstrap['ci_95_high']:+.5f}]), "
        f"p(no improvement) = {bootstrap['p_value_no_improvement_one_sided']:.3f}"
    )


def _save_equity_curve_plot(db, selected_model: str, out_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    per_stock = backtest._per_stock_backtest_frames(db)
    series = {
        "ML strategy": backtest._ml_strategy_returns(per_stock, selected_model),
        "Buy & hold": backtest._buy_and_hold_returns(per_stock),
        "Momentum": backtest._momentum_strategy_returns(per_stock),
    }

    fig, ax = plt.subplots(figsize=(9, 5))
    for label, returns in series.items():
        equity = (1 + returns).cumprod()
        ax.plot(equity.values, label=label)
    ax.set_xlabel("Pooled out-of-sample observation index (not a calendar axis -- see docs/methodology.md)")
    ax.set_ylabel("Cumulative equity (starting at 1.0)")
    ax.set_title("Backtest Equity Curves -- Pooled Purged Walk-Forward Out-of-Sample")
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
