"""Inference layer for the stock direction classifier.

Loads the model trained by ``app.ml.train`` and produces a directional
estimate (POSITIVE / NEGATIVE / NEUTRAL) with a probability and an explicit,
documented confidence bucket. This module never invents accuracy numbers --
confidence is derived purely from how far the predicted probability sits
from the 0.5 decision boundary.

Phase 17: ``important_features`` is now derived from a PER-PREDICTION SHAP
explanation (app.ml.shap_explain) -- genuinely specific to this stock's
current feature values -- rather than Phase 6's static, training-run-wide
``feature_importance_rank`` (the same 3 features for every stock). See
docs/adr/0006-shap-per-prediction-explanations.md. If SHAP explanation
isn't available (e.g. no background sample saved, an older model
artifact), this falls back to the old static ranking rather than failing
the prediction -- a prediction is still useful without its explanation.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import joblib
from sqlalchemy.orm import Session

from app.ml import prediction_ledger, shap_explain
from app.ml.features import FEATURE_COLUMNS, build_feature_frame
from app.ml.train import MODEL_PATH, load_metadata
from app.models.prediction import Confidence, Direction, Prediction
from app.models.stock import Stock
from app.services import analytics

FEATURE_LABELS = {
    "return_1d": "Recent price momentum",
    "return_5d": "5-day momentum",
    "sma5_ratio": "Short-term moving average trend",
    "sma20_ratio": "Moving average trend",
    "ema20_ratio": "Exponential moving average trend",
    "rsi_14": "RSI (relative strength)",
    "volatility_10d": "Volatility",
    "momentum_10d": "Momentum",
    "volume_ratio": "Trading volume",
}


class ModelNotTrainedError(RuntimeError):
    pass


def _confidence_from_probability(probability: float) -> Confidence:
    distance = abs(probability - 0.5)
    if distance >= 0.15:
        return Confidence.HIGH
    if distance >= 0.07:
        return Confidence.MEDIUM
    return Confidence.LOW


def _direction_from_probability(probability: float) -> Direction:
    if probability >= 0.55:
        return Direction.POSITIVE
    if probability <= 0.45:
        return Direction.NEGATIVE
    return Direction.NEUTRAL


class PredictionService:
    def __init__(self, db: Session):
        self.db = db
        if not MODEL_PATH.exists():
            raise ModelNotTrainedError(
                "No trained model found. Run the seed/training script first: "
                "python -m app.data.seed"
            )
        # As of Phase 6 this is a CalibratedClassifierCV wrapping either a
        # Pipeline(scaler, clf) or a tree-based model directly -- it always
        # takes raw (unscaled) feature rows; any scaling happens inside the
        # pipeline, so there is no separate scaler artifact to load anymore.
        self.model = joblib.load(MODEL_PATH)
        self.metadata = load_metadata() or {}
        self.model_name = self.metadata.get("selected_model", "unknown")
        self.model_version = self.metadata.get("model_version", "unknown")

    def predict_for_stock(self, stock: Stock) -> Prediction:
        from app.models.stock import MarketData

        bars = (
            self.db.query(MarketData)
            .filter(MarketData.stock_id == stock.id)
            .order_by(MarketData.date.asc())
            .all()
        )
        if len(bars) < 30:
            raise ValueError(f"Not enough history to predict for {stock.symbol}")

        df = analytics.ohlcv_to_frame(bars)
        feat = build_feature_frame(df)
        latest = feat.dropna(subset=FEATURE_COLUMNS).iloc[[-1]]
        X = latest[FEATURE_COLUMNS]

        probability = float(self.model.predict_proba(X)[0, 1])
        direction = _direction_from_probability(probability)
        confidence = _confidence_from_probability(probability)

        shap_detail = None
        try:
            shap_detail = shap_explain.explain(self.model_name, self.model, X)
            top_features = sorted(
                shap_detail["shap_values"], key=lambda f: -abs(shap_detail["shap_values"][f])
            )[:3]
        except shap_explain.ShapExplanationUnavailable:
            top_features = self.metadata.get("feature_importance_rank", FEATURE_COLUMNS)[:3]
        important_features = [FEATURE_LABELS.get(f, f) for f in top_features]

        today = date.today()
        existing = (
            self.db.query(Prediction)
            .filter(
                Prediction.stock_id == stock.id,
                Prediction.model_name == self.model_name,
                Prediction.prediction_date == today,
            )
            .first()
        )
        is_new_prediction = existing is None
        if existing:
            existing.direction = direction
            existing.probability = probability
            existing.confidence = confidence
            existing.important_features = json.dumps(important_features)
            existing.model_version = self.model_version
            prediction = existing
        else:
            prediction = Prediction(
                stock_id=stock.id,
                model_name=self.model_name,
                model_version=self.model_version,
                direction=direction,
                probability=probability,
                confidence=confidence,
                important_features=json.dumps(important_features),
                prediction_date=today,
            )
            self.db.add(prediction)
        self.db.commit()
        self.db.refresh(prediction)

        # Phase 18: append to the public, hash-chained ledger -- but only
        # the FIRST time today's prediction for this (stock, model) is
        # made, not on every subsequent cached read/recompute of the same
        # day's prediction (append_prediction_entry also independently
        # guards against duplicates, this just avoids the redundant call).
        if is_new_prediction:
            prediction_ledger.append_prediction_entry(self.db, stock, prediction)
        # Transient (NOT persisted/mapped) attribute: the full per-feature
        # SHAP breakdown, for the API route to expose. Not stored in the DB
        # -- recomputed fresh (cheaply, see shap_explain.py) on every call
        # rather than adding a schema column for it.
        prediction.shap_detail = shap_detail
        return prediction
