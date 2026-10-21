"""Backtesting for the next-day direction classifier and its baselines
(Phase 13). Produces an honest, reproducible comparison of:

  - the ML strategy (long when the calibrated model predicts POSITIVE
    with probability >= 0.55, the same threshold app.ml.predict uses for
    the POSITIVE direction label; flat otherwise) against
  - buy-and-hold and naive-momentum baselines,

all evaluated on the exact same purged walk-forward OUT-OF-SAMPLE test
rows (app.ml.features.purged_walk_forward_splits), so no comparison uses
data a real deployment wouldn't have had at the time.

Reports, for each strategy: annualized return/volatility/Sharpe, max
drawdown, historical VaR/CVaR (reusing app.portfolio.risk_service's exact
pure functions), and the Probabilistic/Deflated Sharpe Ratio (PSR/DSR,
Bailey & Lopez de Prado 2014) for the ML strategy specifically. Also runs
a paired bootstrap test (ML strategy vs. buy-and-hold) and a feature-group
ablation.

IMPORTANT HONESTY NOTES (see docs/limitations.md for the full list):
  - The PSR/DSR formula below was NOT independently verified against the
    original Bailey & Lopez de Prado (2014) paper -- this sandbox has no
    network access to fetch it. It was implemented from a formula
    cross-checked across three independent secondary sources (Quantt,
    endgame-ml, fynance documentation) that converged on the same
    structure; it has not been checked against those libraries' own
    reference numerical output.
  - The "N trials" used for the DSR's deflation benchmark is the 3
    candidate model types from Phase 6 (logistic_regression,
    random_forest, xgboost) -- an honestly tiny trial count for an
    asymptotic extreme-value approximation that's designed for much
    larger N. The DSR number this produces demonstrates the methodology
    working end-to-end; it should not be read as a statistically reliable
    multiple-testing correction at N=3.
  - This all runs on synthetic DEV_SAMPLE data (Phase 4's documented
    limitation) -- a backtest on synthetic random-walk data measures
    whether the methodology is implemented correctly, not whether the
    strategy would work on real markets.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import roc_auc_score
from sqlalchemy.orm import Session

from app.ml.features import FEATURE_COLUMNS, LABEL_HORIZON_DAYS, build_feature_frame, purged_walk_forward_splits
from app.ml.train import CALIBRATION_METHOD, MIN_ROWS_PER_STOCK, N_SPLITS, _make_candidates
from app.models.stock import MarketData, Stock
from app.portfolio.risk_service import historical_var_cvar
from app.services import analytics

POSITIVE_THRESHOLD = 0.55  # matches app.ml.predict's POSITIVE direction cutoff
EULER_MASCHERONI = 0.5772156649015329
TRIAL_MODEL_NAMES = ("logistic_regression", "random_forest", "xgboost")

FEATURE_GROUPS: dict[str, list[str]] = {
    "returns": ["return_1d", "return_5d"],
    "moving_averages": ["sma5_ratio", "sma20_ratio", "ema20_ratio"],
    "oscillators": ["rsi_14", "momentum_10d"],
    "volatility": ["volatility_10d"],
    "volume": ["volume_ratio"],
}


def _per_stock_backtest_frames(db: Session) -> dict[str, pd.DataFrame]:
    """Like app.ml.train's feature-frame builder, but also carries the
    continuous next_day_return needed for strategy P&L (train.py's
    binary `label` column alone can't tell you HOW MUCH a day moved)."""
    frames = {}
    for stock in db.query(Stock).all():
        bars = (
            db.query(MarketData)
            .filter(MarketData.stock_id == stock.id)
            .order_by(MarketData.date.asc())
            .all()
        )
        if len(bars) < MIN_ROWS_PER_STOCK:
            continue
        df = analytics.ohlcv_to_frame(bars)
        feat = build_feature_frame(df)
        feat["next_day_return"] = df["close"].shift(-1) / df["close"] - 1
        feat = feat.dropna(subset=FEATURE_COLUMNS + ["label", "next_day_return"])
        if len(feat) < MIN_ROWS_PER_STOCK:
            continue
        frames[stock.symbol] = feat.sort_values("date").reset_index(drop=True)
    if not frames:
        raise ValueError("No market data available to backtest. Seed the database first.")
    return frames


def _pooled_folds(per_stock: dict[str, pd.DataFrame], n_splits: int = N_SPLITS):
    """Same pooling logic as app.ml.train._pooled_folds, duplicated here
    since these frames carry the extra next_day_return column."""
    per_stock_folds = {
        symbol: list(purged_walk_forward_splits(df, n_splits=n_splits, embargo=LABEL_HORIZON_DAYS))
        for symbol, df in per_stock.items()
    }
    max_folds = max((len(f) for f in per_stock_folds.values()), default=0)
    for fold_idx in range(max_folds):
        train_parts, test_parts = [], []
        for symbol, folds in per_stock_folds.items():
            if fold_idx >= len(folds):
                continue
            tr, te = folds[fold_idx]
            train_parts.append(tr)
            test_parts.append(te)
        if not train_parts:
            continue
        yield pd.concat(train_parts, ignore_index=True), pd.concat(test_parts, ignore_index=True)


def _ml_strategy_returns(per_stock: dict[str, pd.DataFrame], model_name: str, threshold: float = POSITIVE_THRESHOLD) -> pd.Series:
    """Retrain `model_name` (calibrated, matching deployment) fresh on
    each fold's train split, predict on that fold's held-out test split,
    and return the pooled out-of-sample strategy daily-return series:
    the realized next-day return on days the model says POSITIVE with
    probability >= threshold, 0 (flat) otherwise.

    Uses a plain positional (RangeIndex) series, NOT a date index --
    pooling across multiple stocks produces many rows sharing the same
    calendar date, which breaks pandas' label-based alignment. Every
    pooling function here iterates `_pooled_folds(per_stock)` the same
    deterministic way, so row N means the same (fold, stock, row-within-
    fold) across all three strategies' series -- that's what makes the
    paired bootstrap comparison in paired_bootstrap_test() valid."""
    pieces = []
    for train_df, test_df in _pooled_folds(per_stock):
        X_train, y_train = train_df[FEATURE_COLUMNS], train_df["label"]
        X_test = test_df[FEATURE_COLUMNS]
        model = CalibratedClassifierCV(_make_candidates()[model_name], method=CALIBRATION_METHOD, cv=3)
        model.fit(X_train, y_train)
        proba = model.predict_proba(X_test)[:, 1]
        signal = (proba >= threshold).astype(float)
        pieces.append(pd.Series(signal * test_df["next_day_return"].values))
    return pd.concat(pieces, ignore_index=True)


def _buy_and_hold_returns(per_stock: dict[str, pd.DataFrame]) -> pd.Series:
    """Pooled, over the SAME test-fold rows as the ML strategy (for a fair
    paired comparison), always 'long'. See _ml_strategy_returns docstring
    on why this is a positional, not date-indexed, series."""
    pieces = [pd.Series(test_df["next_day_return"].values) for _, test_df in _pooled_folds(per_stock)]
    return pd.concat(pieces, ignore_index=True)


def _momentum_strategy_returns(per_stock: dict[str, pd.DataFrame]) -> pd.Series:
    """Long when yesterday's return was positive, flat otherwise -- same
    test rows, same positional-indexing rationale as _ml_strategy_returns."""
    pieces = []
    for _, test_df in _pooled_folds(per_stock):
        signal = (test_df["return_1d"] > 0).astype(float).values
        pieces.append(pd.Series(signal * test_df["next_day_return"].values))
    return pd.concat(pieces, ignore_index=True)


def daily_sharpe(returns: pd.Series, daily_risk_free: float = 0.0) -> float:
    """PER-PERIOD (not annualized) Sharpe ratio -- the PSR/DSR formula's
    sqrt(T-1) term does its own scaling and must not be fed an already-
    annualized Sharpe (annualizing first would double-count)."""
    excess = returns.dropna() - daily_risk_free
    std = excess.std()
    if std == 0 or np.isnan(std) or len(excess) < 2:
        return 0.0
    return float(excess.mean() / std)


def compute_expected_max_sharpe_under_null(n_trials: int, trial_sharpe_variance: float) -> float:
    """SR0: the expected maximum per-period Sharpe ratio across
    `n_trials` independent, zero-skill trials -- the deflation benchmark.
    Bailey & Lopez de Prado (2014); see module docstring for the
    verification caveat."""
    if n_trials < 2 or trial_sharpe_variance < 0:
        return 0.0
    gamma = EULER_MASCHERONI
    term1 = (1 - gamma) * stats.norm.ppf(1 - 1 / n_trials)
    term2 = gamma * stats.norm.ppf(1 - 1 / (n_trials * math.e))
    return float(math.sqrt(trial_sharpe_variance) * (term1 + term2))


def compute_probabilistic_sharpe_ratio(sharpe_hat: float, benchmark_sharpe: float, n_obs: int, skew: float, kurtosis: float) -> float:
    """PSR(SR*). `sharpe_hat`/`benchmark_sharpe` must be PER-PERIOD.
    `kurtosis` must be Pearson/raw convention (normal distribution = 3),
    NOT excess kurtosis -- callers must add 3 to scipy's excess kurtosis
    before passing it in. See module docstring for the verification caveat."""
    if n_obs < 2:
        return 0.5
    denom_sq = 1 - skew * sharpe_hat + ((kurtosis - 1) / 4) * sharpe_hat**2
    denom = math.sqrt(max(denom_sq, 1e-12))
    z = (sharpe_hat - benchmark_sharpe) * math.sqrt(n_obs - 1) / denom
    return float(stats.norm.cdf(z))


def compute_deflated_sharpe_ratio(
    sharpe_hat: float, n_trials: int, trial_sharpe_variance: float, n_obs: int, skew: float, kurtosis: float
) -> dict:
    """DSR = PSR evaluated at SR0 instead of 0. Returns both the
    benchmark SR0 and the resulting DSR (a probability in [0, 1], not a
    Sharpe ratio in the usual units -- it's the probability the true
    Sharpe exceeds what N unskilled trials would be expected to produce
    by chance)."""
    sr0 = compute_expected_max_sharpe_under_null(n_trials, trial_sharpe_variance)
    dsr = compute_probabilistic_sharpe_ratio(sharpe_hat, sr0, n_obs, skew, kurtosis)
    return {"sr0_per_period": sr0, "dsr": dsr}


def _strategy_summary(name: str, returns: pd.Series) -> dict:
    annualized_return = float((1 + returns).prod() ** (252 / len(returns)) - 1) if len(returns) > 0 else 0.0
    annualized_vol = float(returns.std() * np.sqrt(252))
    sharpe = analytics.sharpe_ratio(returns)
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    max_dd = float(drawdown.min()) if len(drawdown) > 0 else 0.0
    var_95, cvar_95 = historical_var_cvar(returns, 0.95)
    return {
        "strategy": name,
        "n_observations": int(len(returns)),
        "annualized_return": round(annualized_return, 4),
        "annualized_volatility": round(annualized_vol, 4),
        "sharpe_ratio": round(sharpe, 3),
        "max_drawdown": round(max_dd, 4),
        "var_95": var_95,
        "cvar_95": cvar_95,
    }


def paired_bootstrap_test(strategy_returns: pd.Series, baseline_returns: pd.Series, n_resamples: int = 1000, seed: int = 42) -> dict:
    """Paired bootstrap: resample matched (strategy, baseline) daily
    return pairs with replacement `n_resamples` times, compute the
    per-period Sharpe difference each time. Reports the mean difference,
    a 95% bootstrap confidence interval, and the fraction of resamples
    where the strategy's Sharpe did NOT exceed the baseline's (a one-sided
    bootstrap p-value against the null of no improvement)."""
    aligned = pd.concat([strategy_returns, baseline_returns], axis=1, join="inner").dropna()
    aligned.columns = ["strategy", "baseline"]
    n = len(aligned)
    if n < 10:
        return {"note": "Not enough paired observations for a meaningful bootstrap.", "n_paired_observations": n}

    rng = np.random.default_rng(seed)
    diffs = np.empty(n_resamples)
    for i in range(n_resamples):
        idx = rng.integers(0, n, size=n)
        sample = aligned.iloc[idx]
        diffs[i] = daily_sharpe(sample["strategy"]) - daily_sharpe(sample["baseline"])

    p_value_no_improvement = float(np.mean(diffs <= 0))
    return {
        "n_paired_observations": n,
        "n_resamples": n_resamples,
        "mean_sharpe_diff_per_period": round(float(np.mean(diffs)), 5),
        "ci_95_low": round(float(np.percentile(diffs, 2.5)), 5),
        "ci_95_high": round(float(np.percentile(diffs, 97.5)), 5),
        "p_value_no_improvement_one_sided": round(p_value_no_improvement, 4),
    }


def run_ablation(db: Session, model_name: str) -> list[dict]:
    """Removes one feature group at a time, re-runs the SAME purged
    walk-forward CV (uncalibrated, matching Phase 6's candidate-selection
    methodology -- calibration doesn't affect AUC ranking), and reports
    the mean validation AUC for `model_name` with that group missing."""
    per_stock = _per_stock_backtest_frames(db)

    def _mean_val_auc(feature_columns: list[str]) -> float:
        aucs = []
        for train_df, test_df in _pooled_folds(per_stock):
            X_train, y_train = train_df[feature_columns], train_df["label"]
            X_test, y_test = test_df[feature_columns], test_df["label"]
            model = _make_candidates()[model_name]
            model.fit(X_train, y_train)
            proba = model.predict_proba(X_test)[:, 1]
            auc = roc_auc_score(y_test, proba) if y_test.nunique() > 1 else 0.5
            aucs.append(float(auc))
        return float(np.mean(aucs)) if aucs else 0.5

    full_auc = _mean_val_auc(FEATURE_COLUMNS)
    results = [{"feature_group_removed": None, "remaining_features": FEATURE_COLUMNS, "mean_val_auc": round(full_auc, 4), "delta_vs_full": 0.0}]
    for group_name, group_cols in FEATURE_GROUPS.items():
        remaining = [c for c in FEATURE_COLUMNS if c not in group_cols]
        if not remaining:
            continue
        auc = _mean_val_auc(remaining)
        results.append(
            {
                "feature_group_removed": group_name,
                "remaining_features": remaining,
                "mean_val_auc": round(auc, 4),
                "delta_vs_full": round(auc - full_auc, 4),
            }
        )
    return results


def run_backtest(db: Session, selected_model_name: str) -> dict:
    """Top-level entry point. `selected_model_name` should be the model
    type Phase 6 actually selected (from model_metadata.json), so the
    headline ML-strategy numbers describe the real deployed model type,
    not an arbitrary choice."""
    per_stock = _per_stock_backtest_frames(db)

    trial_returns = {name: _ml_strategy_returns(per_stock, name) for name in TRIAL_MODEL_NAMES}
    trial_sharpes = {name: daily_sharpe(r) for name, r in trial_returns.items()}

    ml_returns = trial_returns[selected_model_name]
    buy_hold_returns = _buy_and_hold_returns(per_stock)
    momentum_returns = _momentum_strategy_returns(per_stock)

    summaries = [
        _strategy_summary("ml_strategy", ml_returns),
        _strategy_summary("buy_and_hold", buy_hold_returns),
        _strategy_summary("momentum", momentum_returns),
    ]

    clean_ml_returns = ml_returns.dropna()
    skew = float(stats.skew(clean_ml_returns)) if len(clean_ml_returns) > 2 else 0.0
    excess_kurtosis = float(stats.kurtosis(clean_ml_returns, fisher=True)) if len(clean_ml_returns) > 2 else 0.0
    pearson_kurtosis = excess_kurtosis + 3.0

    trial_sharpe_values = list(trial_sharpes.values())
    dsr_result = compute_deflated_sharpe_ratio(
        sharpe_hat=trial_sharpes[selected_model_name],
        n_trials=len(trial_sharpe_values),
        trial_sharpe_variance=float(np.var(trial_sharpe_values, ddof=1)) if len(trial_sharpe_values) > 1 else 0.0,
        n_obs=len(clean_ml_returns),
        skew=skew,
        kurtosis=pearson_kurtosis,
    )

    bootstrap = paired_bootstrap_test(ml_returns, buy_hold_returns)
    ablation = run_ablation(db, selected_model_name)

    return {
        "selected_model": selected_model_name,
        "positive_threshold": POSITIVE_THRESHOLD,
        "strategy_summaries": summaries,
        "trial_sharpes_per_period": {k: round(v, 5) for k, v in trial_sharpes.items()},
        "deflated_sharpe_ratio": {
            **dsr_result,
            "n_trials": len(trial_sharpe_values),
            "skewness": round(skew, 4),
            "pearson_kurtosis": round(pearson_kurtosis, 4),
            "note": "N=3 trials is far smaller than this asymptotic approximation is designed for -- see module docstring.",
        },
        "paired_bootstrap_vs_buy_and_hold": bootstrap,
        "ablation": ablation,
    }
