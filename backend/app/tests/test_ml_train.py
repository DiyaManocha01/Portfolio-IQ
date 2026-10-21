"""Tests for the Phase 6 ML training pipeline: baselines, versioning, and an
end-to-end smoke test against the seeded database (purged walk-forward CV +
calibration actually running, not just mocked).
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.ml import train as train_module
from app.ml.train import (
    _majority_class_baseline,
    _model_version,
    _momentum_baseline,
    train_and_select_model,
)


def test_majority_class_baseline_reports_training_majority():
    y_train = pd.Series([1.0, 1.0, 1.0, 0.0])  # 75% positive
    y_test = pd.Series([1.0, 1.0, 0.0, 1.0])  # 3/4 match "always predict 1"
    result = _majority_class_baseline(y_train, y_test)
    assert result["majority_class"] == 1.0
    assert result["accuracy"] == pytest.approx(0.75)
    assert result["auc"] == 0.5  # reported by convention, not computed


def test_momentum_baseline_predicts_sign_of_todays_return():
    train_df = pd.DataFrame({"return_1d": [0.01, -0.01], "label": [1.0, 0.0]})
    test_df = pd.DataFrame(
        {
            "return_1d": [0.02, -0.03, 0.01, -0.01],
            "label": [1.0, 0.0, 1.0, 1.0],  # 3/4 agree with sign(return_1d)
        }
    )
    result = _momentum_baseline(train_df, test_df)
    assert result["accuracy"] == pytest.approx(0.75)
    assert 0 <= result["auc"] <= 1


def test_model_version_is_deterministic_for_same_inputs():
    v1 = _model_version("xgboost")
    v2 = _model_version("xgboost")
    assert v1 == v2
    assert len(v1) == 12


def test_model_version_differs_by_selected_model():
    assert _model_version("xgboost") != _model_version("random_forest")


def test_model_version_changes_if_feature_columns_change(monkeypatch):
    v_before = _model_version("xgboost")
    monkeypatch.setattr(train_module, "FEATURE_COLUMNS", train_module.FEATURE_COLUMNS + ["new_feature"])
    v_after = _model_version("xgboost")
    assert v_before != v_after


def test_train_and_select_model_end_to_end(db_session):
    """Real smoke test: runs the full purged-walk-forward + calibration
    pipeline against the already-seeded database (not mocked), and checks
    the metadata shape is exactly what predict.py and the API depend on.
    """
    metadata = train_and_select_model(db_session)

    assert metadata["selected_model"] in {"logistic_regression", "random_forest", "xgboost"}
    assert len(metadata["model_version"]) == 12

    cv = metadata["cross_validation"]["per_candidate"]
    assert set(cv.keys()) == {"logistic_regression", "random_forest", "xgboost"}
    for candidate_metrics in cv.values():
        assert candidate_metrics["n_folds"] >= 1
        assert 0 <= candidate_metrics["mean_val_auc"] <= 1

    final = metadata["final_holdout_test"]
    assert 0 <= final["test_auc_calibrated"] <= 1
    assert final["n_test_rows"] > 0

    baselines = metadata["baselines"]
    assert "majority_class" in baselines and "momentum" in baselines

    assert train_module.MODEL_PATH.exists()
    assert train_module.CALIBRATION_PLOT_PATH.exists()
