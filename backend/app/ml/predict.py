"""Inference layer for the stock direction classifier.

Loads the model trained by ``app.ml.train`` and produces a directional
estimate (POSITIVE / NEGATIVE / NEUTRAL) with a probability and an explicit,
documented confidence bucket. This module never invents accuracy numbers --
confidence is derived purely from how far the predicted probability sits
from the 0.5 decision boundary.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import joblib
from sqlalchemy.orm import Session

from app.ml.features import FEATURE_COLUMNS, build_feature_frame
from app.ml.train import METADATA_PATH, MODEL_PATH, SCALER_PATH, load_metadata
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
        if not (MODEL_PATH.exists() and SCALER_PATH.exists()):
            raise ModelNotTrainedError(
                "No trained model found. Run the seed/training script first: "
                "python -m app.data.seed"
            )
        self.model = joblib.load(MODEL_PATH)
        self.scaler = joblib.load(SCALER_PATH)
        self.metadata = load_metadata() or {}
        self.model_name = self.metadata.get("selected_model", "unknown")

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

        if self.model_name == "logistic_regression":
            X_input = self.scaler.transform(X)
        else:
            X_input = X

        probability = float(self.model.predict_proba(X_input)[0, 1])
        direction = _direction_from_probability(probability)
        confidence = _confidence_from_probability(probability)

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
        if existing:
            existing.direction = direction
            existing.probability = probability
            existing.confidence = confidence
            existing.important_features = json.dumps(important_features)
            prediction = existing
        else:
            prediction = Prediction(
                stock_id=stock.id,
                model_name=self.model_name,
                direction=direction,
                probability=probability,
                confidence=confidence,
                important_features=json.dumps(important_features),
                prediction_date=today,
            )
            self.db.add(prediction)
        self.db.commit()
        self.db.refresh(prediction)
        return prediction
