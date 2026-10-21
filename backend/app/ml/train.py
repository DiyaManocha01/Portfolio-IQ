"""Training pipeline for the next-day stock direction classifier (Phase 6).

Supersedes the Phase 1-3 pipeline's simple chronological 70/15/15 split --
see docs/adr/0003-ml-pipeline-rebuild.md for why, and
docs/methodology.md Section 3 for the full methodology this implements:

  1. Purged walk-forward cross-validation (per stock, embargo = label
     horizon) for model selection, instead of one single split.
  2. The winning model type is calibrated (Platt/sigmoid scaling) so its
     predicted probabilities are meaningfully interpretable as
     probabilities, not just a ranking score.
  3. A reliability (calibration) diagram is saved alongside the model.
  4. Two baselines -- majority-class and naive momentum -- are always
     computed on the exact same held-out test set as the real model, so an
     accuracy number is never reported without honest context for what a
     trivial predictor would already achieve.
  5. The saved model_version is a content hash of the methodology+features
     that produced it (not an arbitrary incrementing counter), so it
     changes automatically if this pipeline's logic changes, and two
     predictions tagged with the same version are guaranteed to have come
     from the same training methodology.

The selected (calibrated) model is persisted to disk (joblib) along with
metadata describing cross-validated and final held-out performance, so the
API layer never retrains on the fly and never fabricates accuracy numbers.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy.orm import Session
from xgboost import XGBClassifier

from app.ml.features import (
    FEATURE_COLUMNS,
    LABEL_HORIZON_DAYS,
    build_feature_frame,
    purged_walk_forward_splits,
)
from app.models.stock import MarketData, Stock
from app.services import analytics

MODEL_DIR = Path(__file__).resolve().parent.parent / "data" / "models"
MODEL_PATH = MODEL_DIR / "direction_model.joblib"
METADATA_PATH = MODEL_DIR / "model_metadata.json"
CALIBRATION_PLOT_PATH = MODEL_DIR / "calibration_plot.png"
SHAP_BACKGROUND_PATH = MODEL_DIR / "shap_background.joblib"
SHAP_BACKGROUND_SAMPLE_SIZE = 100  # Phase 17: pooled training rows used as the SHAP explainer's baseline

N_SPLITS = 5
CALIBRATION_METHOD = "sigmoid"  # Platt scaling -- safer than isotonic on our modest sample sizes
MIN_ROWS_PER_STOCK = 80  # need enough rows for N_SPLITS+1 blocks to each be non-trivial


def _make_candidates() -> dict:
    """Fresh, unfitted estimator instances -- must be called again for every fold
    (sklearn estimators are mutated in place by .fit(), so one shared
    instance reused across folds would silently leak state between them)."""
    return {
        "logistic_regression": Pipeline(
            [
                ("scaler", StandardScaler()),
                ("clf", LogisticRegression(max_iter=500, class_weight="balanced")),
            ]
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=200, max_depth=5, min_samples_leaf=10, random_state=42, class_weight="balanced"
        ),
        "xgboost": XGBClassifier(
            n_estimators=200,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            eval_metric="logloss",
            random_state=42,
        ),
    }


def _per_stock_feature_frames(db: Session) -> dict[str, pd.DataFrame]:
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
        feat = build_feature_frame(df).dropna(subset=FEATURE_COLUMNS + ["label"])
        if len(feat) < MIN_ROWS_PER_STOCK:
            continue
        frames[stock.symbol] = feat.sort_values("date").reset_index(drop=True)
    if not frames:
        raise ValueError("No market data available to train on. Seed the database first.")
    return frames


def _pooled_folds(per_stock: dict[str, pd.DataFrame], n_splits: int = N_SPLITS):
    """Yields (train_df, test_df) pooled across every stock, fold by fold.

    Each stock contributes its own purged-walk-forward fold independently
    (so one stock's shorter history doesn't truncate another's), then
    same-fold-index results are concatenated across stocks.
    """
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
        if not train_parts or not test_parts:
            continue
        yield pd.concat(train_parts, ignore_index=True), pd.concat(test_parts, ignore_index=True)


def _xy(df: pd.DataFrame):
    return df[FEATURE_COLUMNS], df["label"]


def _majority_class_baseline(y_train: pd.Series, y_test: pd.Series) -> dict:
    majority = float(y_train.mode().iloc[0])
    preds = pd.Series([majority] * len(y_test))
    acc = accuracy_score(y_test, preds)
    return {
        "accuracy": float(acc),
        "auc": 0.5,  # a constant predictor has no discriminative power -- reported, not computed via roc_auc_score (which errors on a degenerate input)
        "majority_class": majority,
        "note": "Predicts the training set's majority class for every row. AUC is undefined for a constant predictor; 0.5 (no skill) is reported by convention, not computed.",
    }


def _momentum_baseline(train_df: pd.DataFrame, test_df: pd.DataFrame) -> dict:
    """Naive persistence baseline: predict tomorrow's direction = sign of today's return."""
    score = test_df["return_1d"]
    y_test = test_df["label"]
    preds = (score > 0).astype(float)
    acc = accuracy_score(y_test, preds)
    auc = float(roc_auc_score(y_test, score)) if y_test.nunique() > 1 else 0.5
    return {
        "accuracy": float(acc),
        "auc": auc,
        "note": "Predicts 'up' when today's return was positive, 'down' otherwise; AUC uses today's raw return as a ranking score.",
    }


def _model_version(selected_model: str) -> str:
    """Content hash of the methodology, not an arbitrary counter -- changes
    automatically if features, split params, or the chosen model type change."""
    fingerprint = json.dumps(
        {
            "features": FEATURE_COLUMNS,
            "label_horizon_days": LABEL_HORIZON_DAYS,
            "n_splits": N_SPLITS,
            "calibration_method": CALIBRATION_METHOD,
            "selected_model": selected_model,
        },
        sort_keys=True,
    )
    return hashlib.sha256(fingerprint.encode()).hexdigest()[:12]


def _save_calibration_plot(y_true: pd.Series, uncalibrated_proba: np.ndarray, calibrated_proba: np.ndarray) -> None:
    import matplotlib

    matplotlib.use("Agg")  # headless -- no display available in this environment
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot([0, 1], [0, 1], linestyle="--", color="gray", label="Perfectly calibrated")

    for proba, label, marker in [(uncalibrated_proba, "Uncalibrated", "o"), (calibrated_proba, "Calibrated (sigmoid)", "s")]:
        if pd.Series(y_true).nunique() > 1:
            frac_pos, mean_pred = calibration_curve(y_true, proba, n_bins=8, strategy="quantile")
            ax.plot(mean_pred, frac_pos, marker=marker, label=label)

    ax.set_xlabel("Mean predicted probability")
    ax.set_ylabel("Fraction of positives (observed)")
    ax.set_title("Reliability Diagram -- Held-Out Test Set")
    ax.legend(loc="best")
    fig.tight_layout()
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(CALIBRATION_PLOT_PATH, dpi=120)
    plt.close(fig)


def train_and_select_model(db: Session) -> dict:
    per_stock = _per_stock_feature_frames(db)

    # --- Step 1: purged walk-forward CV across all folds, for every candidate ---
    fold_results: dict[str, list[dict]] = {name: [] for name in _make_candidates()}
    last_fold = None
    for train_df, test_df in _pooled_folds(per_stock, n_splits=N_SPLITS):
        last_fold = (train_df, test_df)
        X_train, y_train = _xy(train_df)
        X_test, y_test = _xy(test_df)
        for name, model in _make_candidates().items():
            model.fit(X_train, y_train)
            proba = model.predict_proba(X_test)[:, 1]
            preds = (proba >= 0.5).astype(int)
            auc = roc_auc_score(y_test, proba) if y_test.nunique() > 1 else 0.5
            acc = accuracy_score(y_test, preds)
            fold_results[name].append({"val_auc": float(auc), "val_accuracy": float(acc), "n_test_rows": len(test_df)})

    if last_fold is None:
        raise ValueError("Not enough history across seeded stocks to form even one walk-forward fold.")

    mean_cv_metrics = {
        name: {
            "mean_val_auc": float(np.mean([f["val_auc"] for f in folds])),
            "mean_val_accuracy": float(np.mean([f["val_accuracy"] for f in folds])),
            "n_folds": len(folds),
            "per_fold": folds,
        }
        for name, folds in fold_results.items()
    }
    best_name = max(mean_cv_metrics, key=lambda n: mean_cv_metrics[n]["mean_val_auc"])

    # --- Step 2: final honest held-out test = the last (most recent) fold ---
    final_train_df, final_test_df = last_fold
    X_train, y_train = _xy(final_train_df)
    X_test, y_test = _xy(final_test_df)

    # Uncalibrated fit of the winning model type, for feature-importance
    # extraction and as the "before" curve on the calibration plot.
    uncalibrated = _make_candidates()[best_name]
    uncalibrated.fit(X_train, y_train)
    uncalibrated_test_proba = uncalibrated.predict_proba(X_test)[:, 1]

    if hasattr(uncalibrated, "feature_importances_"):
        importances = dict(zip(FEATURE_COLUMNS, [float(x) for x in uncalibrated.feature_importances_]))
    elif isinstance(uncalibrated, Pipeline):
        importances = dict(zip(FEATURE_COLUMNS, [float(abs(x)) for x in uncalibrated.named_steps["clf"].coef_[0]]))
    else:
        importances = dict(zip(FEATURE_COLUMNS, [float(abs(x)) for x in uncalibrated.coef_[0]]))
    top_features = sorted(importances, key=importances.get, reverse=True)

    # Calibrated model: fit fresh (CalibratedClassifierCV fits its own
    # internal folds), this is the artifact actually served.
    calibrated = CalibratedClassifierCV(_make_candidates()[best_name], method=CALIBRATION_METHOD, cv=3)
    calibrated.fit(X_train, y_train)
    calibrated_test_proba = calibrated.predict_proba(X_test)[:, 1]

    test_auc_uncalibrated = float(roc_auc_score(y_test, uncalibrated_test_proba)) if y_test.nunique() > 1 else 0.5
    test_auc_calibrated = float(roc_auc_score(y_test, calibrated_test_proba)) if y_test.nunique() > 1 else 0.5
    test_acc_calibrated = float(accuracy_score(y_test, (calibrated_test_proba >= 0.5).astype(int)))

    _save_calibration_plot(y_test, uncalibrated_test_proba, calibrated_test_proba)

    # --- Step 3: baselines, on the exact same held-out test set ---
    majority_baseline = _majority_class_baseline(y_train, y_test)
    momentum_baseline = _momentum_baseline(final_train_df, final_test_df)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(calibrated, MODEL_PATH)

    # Phase 17: a pooled sample of training feature rows, saved alongside the
    # model, used as the SHAP explainer's background/baseline distribution --
    # tied to the SAME training run's data as the deployed model, not a
    # separately-chosen reference set.
    pooled_all = pd.concat(per_stock.values(), ignore_index=True)
    background_n = min(SHAP_BACKGROUND_SAMPLE_SIZE, len(pooled_all))
    background_sample = pooled_all[FEATURE_COLUMNS].sample(n=background_n, random_state=42)
    joblib.dump(background_sample, SHAP_BACKGROUND_PATH)

    model_version = _model_version(best_name)
    metadata = {
        "selected_model": best_name,
        "model_version": model_version,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "cross_validation": {
            "methodology": (
                f"Purged walk-forward CV, {N_SPLITS} expanding-window folds per stock, "
                f"embargo={LABEL_HORIZON_DAYS} day(s) (equal to the label horizon). "
                "Training rows whose label window overlaps the start of a fold's test "
                "block are dropped. Candidates ranked by mean validation ROC-AUC "
                "across all folds."
            ),
            "per_candidate": mean_cv_metrics,
        },
        "calibration": {
            "method": CALIBRATION_METHOD,
            "note": (
                "scikit-learn's CalibratedClassifierCV uses its own internal "
                "(non-time-aware) k-fold for calibration sub-folds -- a known "
                "simplification; see docs/limitations.md."
            ),
            "plot": str(CALIBRATION_PLOT_PATH.name),
        },
        "final_holdout_test": {
            "test_auc_uncalibrated": test_auc_uncalibrated,
            "test_auc_calibrated": test_auc_calibrated,
            "test_accuracy_calibrated": test_acc_calibrated,
            "n_test_rows": int(len(final_test_df)),
            "n_train_rows": int(len(final_train_df)),
        },
        "baselines": {
            "majority_class": majority_baseline,
            "momentum": momentum_baseline,
        },
        "feature_columns": FEATURE_COLUMNS,
        "feature_importance_rank": top_features,
        "label_horizon_days": LABEL_HORIZON_DAYS,
        "n_splits": N_SPLITS,
    }
    METADATA_PATH.write_text(json.dumps(metadata, indent=2))
    return metadata


def load_metadata() -> dict | None:
    if not METADATA_PATH.exists():
        return None
    return json.loads(METADATA_PATH.read_text())
