"""Training pipeline for the next-day stock direction classifier.

Trains three candidate models (Logistic Regression, Random Forest, XGBoost)
on pooled historical data across all seeded stocks, using a strictly
time-aware (chronological, per-stock) train/validation/test split -- the
data is NEVER randomly shuffled, to avoid look-ahead bias in a financial
time series. The model with the best validation ROC-AUC is selected and
evaluated once on the held-out test split for a final, honest metric.

The selected model is persisted to disk (joblib) along with metadata
describing its validation/test performance, so the API layer never has to
retrain on the fly and never fabricates accuracy numbers.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.preprocessing import StandardScaler
from sqlalchemy.orm import Session
from xgboost import XGBClassifier

from app.ml.features import FEATURE_COLUMNS, build_feature_frame, time_aware_split
from app.models.stock import MarketData, Stock
from app.services import analytics

MODEL_DIR = Path(__file__).resolve().parent.parent / "data" / "models"
MODEL_PATH = MODEL_DIR / "direction_model.joblib"
SCALER_PATH = MODEL_DIR / "direction_scaler.joblib"
METADATA_PATH = MODEL_DIR / "model_metadata.json"


def _pool_training_data(db: Session) -> pd.DataFrame:
    frames = []
    for stock in db.query(Stock).all():
        bars = (
            db.query(MarketData)
            .filter(MarketData.stock_id == stock.id)
            .order_by(MarketData.date.asc())
            .all()
        )
        if len(bars) < 60:
            continue
        df = analytics.ohlcv_to_frame(bars)
        feat = build_feature_frame(df)
        feat["symbol"] = stock.symbol
        frames.append(feat)
    if not frames:
        raise ValueError("No market data available to train on. Seed the database first.")
    return pd.concat(frames, ignore_index=True)


def _split_pooled(pooled: pd.DataFrame):
    """Apply a chronological split independently per symbol, then concatenate.

    This keeps each stock's own timeline intact (no shuffling, no
    look-ahead) while still producing a reasonably sized pooled dataset.
    """
    train_parts, val_parts, test_parts = [], [], []
    for symbol, group in pooled.groupby("symbol"):
        group = group.sort_values("date")
        tr, va, te = time_aware_split(group)
        train_parts.append(tr)
        val_parts.append(va)
        test_parts.append(te)
    return pd.concat(train_parts), pd.concat(val_parts), pd.concat(test_parts)


def _prepare_xy(df: pd.DataFrame):
    clean = df.dropna(subset=FEATURE_COLUMNS + ["label"])
    return clean[FEATURE_COLUMNS], clean["label"]


def train_and_select_model(db: Session) -> dict:
    pooled = _pool_training_data(db)
    train_df, val_df, test_df = _split_pooled(pooled)

    X_train, y_train = _prepare_xy(train_df)
    X_val, y_val = _prepare_xy(val_df)
    X_test, y_test = _prepare_xy(test_df)

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_val_s = scaler.transform(X_val)
    X_test_s = scaler.transform(X_test)

    candidates = {
        "logistic_regression": LogisticRegression(max_iter=500, class_weight="balanced"),
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

    results = {}
    fitted = {}
    for name, model in candidates.items():
        if name == "logistic_regression":
            model.fit(X_train_s, y_train)
            val_proba = model.predict_proba(X_val_s)[:, 1]
        else:
            model.fit(X_train, y_train)
            val_proba = model.predict_proba(X_val)[:, 1]
        val_pred = (val_proba >= 0.5).astype(int)
        auc = roc_auc_score(y_val, val_proba) if y_val.nunique() > 1 else 0.5
        acc = accuracy_score(y_val, val_pred)
        results[name] = {"val_auc": float(auc), "val_accuracy": float(acc)}
        fitted[name] = model

    best_name = max(results, key=lambda n: results[n]["val_auc"])
    best_model = fitted[best_name]

    if best_name == "logistic_regression":
        test_proba = best_model.predict_proba(X_test_s)[:, 1]
    else:
        test_proba = best_model.predict_proba(X_test)[:, 1]
    test_pred = (test_proba >= 0.5).astype(int)
    test_auc = roc_auc_score(y_test, test_proba) if y_test.nunique() > 1 else 0.5
    test_acc = accuracy_score(y_test, test_pred)

    if hasattr(best_model, "feature_importances_"):
        importances = dict(zip(FEATURE_COLUMNS, [float(x) for x in best_model.feature_importances_]))
    else:
        importances = dict(zip(FEATURE_COLUMNS, [float(abs(x)) for x in best_model.coef_[0]]))
    top_features = sorted(importances, key=importances.get, reverse=True)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(best_model, MODEL_PATH)
    joblib.dump(scaler, SCALER_PATH)

    metadata = {
        "selected_model": best_name,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "candidates_val_metrics": results,
        "test_metrics": {"test_auc": float(test_auc), "test_accuracy": float(test_acc)},
        "feature_columns": FEATURE_COLUMNS,
        "feature_importance_rank": top_features,
        "train_rows": int(len(X_train)),
        "val_rows": int(len(X_val)),
        "test_rows": int(len(X_test)),
        "methodology": (
            "Chronological (non-shuffled) split per stock: first 70% of each "
            "stock's history for training, next 15% for validation, final 15% "
            "held out for testing. Model selected by validation ROC-AUC."
        ),
    }
    METADATA_PATH.write_text(json.dumps(metadata, indent=2))
    return metadata


def load_metadata() -> dict | None:
    if not METADATA_PATH.exists():
        return None
    return json.loads(METADATA_PATH.read_text())
