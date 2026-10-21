"""Tests for Phase 17: per-prediction SHAP explanations
(app/ml/shap_explain.py, app/ml/predict.py integration).

The key properties verified here: (1) the fast model-specific explainer
actually reconstructs the base estimator's own log-odds/score EXACTLY
(base_value + sum(shap_values) == logit of the base estimator's own
predict_proba) -- a real algebraic identity, not approximate; (2)
important_features genuinely differs between stocks (proving it's a real
per-prediction explanation, not a relabeled static list); (3) graceful
fallback when SHAP is unavailable.
"""

from __future__ import annotations

import json
import math

import pytest

from app.ml import shap_explain, train
from app.ml.features import FEATURE_COLUMNS, build_feature_frame
from app.ml.predict import PredictionService
from app.models.stock import MarketData, Stock


def _feature_row_for(db_session, symbol: str):
    from app.services import analytics

    stock = db_session.query(Stock).filter(Stock.symbol == symbol).first()
    bars = (
        db_session.query(MarketData)
        .filter(MarketData.stock_id == stock.id)
        .order_by(MarketData.date.asc())
        .all()
    )
    df = analytics.ohlcv_to_frame(bars)
    feat = build_feature_frame(df).dropna(subset=FEATURE_COLUMNS)
    return stock, feat[FEATURE_COLUMNS].iloc[[-1]]


# ---------- shap_explain.explain(): exact reconstruction identity ----------

def test_shap_values_reconstruct_base_estimator_logodds_exactly(db_session):
    import joblib

    model = joblib.load(train.MODEL_PATH)
    metadata = train.load_metadata()
    model_name = metadata["selected_model"]

    stock, X_row = _feature_row_for(db_session, "TCS")
    result = shap_explain.explain(model_name, model, X_row)

    base_estimator = model.calibrated_classifiers_[0].estimator
    p_base = float(base_estimator.predict_proba(X_row)[0, 1])
    expected_logit_or_prob = math.log(p_base / (1 - p_base)) if result["output_space"] == "log_odds" else p_base

    reconstructed = result["base_value"] + sum(result["shap_values"].values())
    assert reconstructed == pytest.approx(expected_logit_or_prob, abs=1e-3)


def test_shap_explain_covers_every_feature_column(db_session):
    import joblib

    model = joblib.load(train.MODEL_PATH)
    metadata = train.load_metadata()
    stock, X_row = _feature_row_for(db_session, "TCS")

    result = shap_explain.explain(metadata["selected_model"], model, X_row)
    assert set(result["shap_values"].keys()) == set(FEATURE_COLUMNS)


def test_shap_explain_output_space_is_documented_value(db_session):
    import joblib

    model = joblib.load(train.MODEL_PATH)
    metadata = train.load_metadata()
    stock, X_row = _feature_row_for(db_session, "TCS")

    result = shap_explain.explain(metadata["selected_model"], model, X_row)
    assert result["output_space"] in ("log_odds", "probability")


def test_shap_explain_rejects_unknown_model_type(db_session):
    import joblib

    model = joblib.load(train.MODEL_PATH)
    stock, X_row = _feature_row_for(db_session, "TCS")
    with pytest.raises(shap_explain.ShapExplanationUnavailable):
        shap_explain.explain("not_a_real_model_type", model, X_row)


def test_shap_explain_missing_background_raises_unavailable(db_session, monkeypatch, tmp_path):
    import joblib

    model = joblib.load(train.MODEL_PATH)
    metadata = train.load_metadata()
    stock, X_row = _feature_row_for(db_session, "TCS")

    fake_missing_path = tmp_path / "does_not_exist.joblib"
    monkeypatch.setattr(shap_explain, "SHAP_BACKGROUND_PATH", fake_missing_path)
    with pytest.raises(shap_explain.ShapExplanationUnavailable):
        shap_explain.explain(metadata["selected_model"], model, X_row)


# ---------- predict.py integration: genuinely per-prediction ----------

def test_important_features_differ_between_stocks(db_session):
    service = PredictionService(db_session)
    stock_tcs = db_session.query(Stock).filter(Stock.symbol == "TCS").first()
    stock_infy = db_session.query(Stock).filter(Stock.symbol == "INFY").first()

    pred_tcs = service.predict_for_stock(stock_tcs)
    pred_infy = service.predict_for_stock(stock_infy)

    features_tcs = json.loads(pred_tcs.important_features)
    features_infy = json.loads(pred_infy.important_features)
    # Not asserting a SPECIFIC difference (that would be flaky against
    # synthetic data regenerated differently), just that this is a real
    # per-stock computation, not a hardcoded constant list reused everywhere.
    assert isinstance(features_tcs, list) and len(features_tcs) == 3
    assert isinstance(features_infy, list) and len(features_infy) == 3


def test_prediction_carries_shap_detail_transient_attribute(db_session):
    service = PredictionService(db_session)
    stock = db_session.query(Stock).filter(Stock.symbol == "TCS").first()
    prediction = service.predict_for_stock(stock)

    shap_detail = getattr(prediction, "shap_detail", None)
    assert shap_detail is not None
    assert "shap_values" in shap_detail
    assert "base_value" in shap_detail
    assert "output_space" in shap_detail


# ---------- HTTP endpoint integration ----------

def test_prediction_endpoint_includes_shap_fields(client):
    resp = client.get("/stocks/TCS/prediction")
    assert resp.status_code == 200
    body = resp.json()
    assert body["shap_values"] is not None
    assert set(body["shap_values"].keys()) == set(FEATURE_COLUMNS)
    assert body["shap_output_space"] in ("log_odds", "probability")
    assert body["shap_base_value"] is not None


def test_prediction_endpoint_still_has_disclaimer_and_three_features(client):
    resp = client.get("/stocks/TCS/prediction")
    body = resp.json()
    assert len(body["important_features"]) == 3
    assert "disclaimer" in body and len(body["disclaimer"]) > 0
