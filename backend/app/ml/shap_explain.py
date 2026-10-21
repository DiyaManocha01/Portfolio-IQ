"""Per-prediction SHAP feature attribution for the direction classifier
(Phase 17). Supersedes the static, training-run-wide `feature_importance_rank`
that Phase 6's `important_features` field was derived from -- see
docs/adr/0006-shap-per-prediction-explanations.md for what this supersedes
and docs/methodology.md Section 14 for the full write-up.

Uses a FAST, model-type-specific exact explainer rather than the generic
`shap.Explainer` (which falls back to a slow permutation approximation --
measured at ~7.5s for a single explanation against this project's models,
vs. single-digit milliseconds for the explainers below):

  - logistic_regression (a scaler+LogisticRegression Pipeline):
    `shap.LinearExplainer` on the fitted LogisticRegression step, applied
    to the scaler-TRANSFORMED feature row (LinearExplainer operates on
    the linear model's own input space, which is standardized, not raw).
  - random_forest / xgboost: `shap.TreeExplainer`, applied directly to
    raw (unscaled) features -- tree models don't need scaling.

SHAP explains the UNCALIBRATED base estimator extracted from the deployed
`CalibratedClassifierCV` (`calibrated_classifiers_[0].estimator`), not the
calibrated model actually served. Calibration (Phase 6: Platt/sigmoid
scaling) is a monotonic 1-D remapping of the base estimator's score, so it
does not change which features matter or their sign/direction -- but it
does mean SHAP's base_value + sum(shap_values) does not reconstruct the
exact final served probability.

IMPORTANT, EXPLICITLY DOCUMENTED CAVEAT: SHAP values are in the base
estimator's NATIVE output space, which differs by model type:
  - random_forest: TreeExplainer's output is naturally in PROBABILITY
    space for this model (a random forest's leaves are themselves
    probability estimates, with no separate margin/log-odds concept).
  - logistic_regression / xgboost: output is in LOG-ODDS (margin) space
    -- verified directly against this project's actual trained models
    (see docs/limitations.md for the measured example). A SHAP value of
    +0.05 does NOT mean "+5 percentage points of probability" for these
    two model types.
This is why `output_space` is reported explicitly on every explanation --
never compare raw SHAP magnitudes across model types without checking it.
"""

from __future__ import annotations

import joblib
import pandas as pd
import shap

from app.ml.features import FEATURE_COLUMNS
from app.ml.train import SHAP_BACKGROUND_PATH

OUTPUT_SPACE_BY_MODEL = {
    "logistic_regression": "log_odds",
    "xgboost": "log_odds",
    "random_forest": "probability",
}


class ShapExplanationUnavailable(RuntimeError):
    """Raised when the background sample or an explainer strategy for the
    deployed model type isn't available -- callers should treat this as
    'no per-prediction explanation this time', not crash the prediction
    endpoint, since the prediction itself doesn't depend on SHAP."""


def _background_sample() -> pd.DataFrame:
    if not SHAP_BACKGROUND_PATH.exists():
        raise ShapExplanationUnavailable(
            f"No SHAP background sample found at {SHAP_BACKGROUND_PATH}. "
            "Retrain the model (python -m app.data.seed) to generate one."
        )
    return joblib.load(SHAP_BACKGROUND_PATH)


def explain(model_name: str, calibrated_model, X_row: pd.DataFrame) -> dict:
    """`calibrated_model` is the deployed CalibratedClassifierCV; `X_row`
    is a single-row DataFrame of raw (unscaled) FEATURE_COLUMNS values --
    the same row passed to calibrated_model.predict_proba().

    Returns {"shap_values": {feature: float}, "base_value": float,
    "output_space": "log_odds" | "probability", "model_name": str}.
    """
    if model_name not in OUTPUT_SPACE_BY_MODEL:
        raise ShapExplanationUnavailable(f"No SHAP explainer strategy defined for model type {model_name!r}.")

    try:
        base_estimator = calibrated_model.calibrated_classifiers_[0].estimator
    except (AttributeError, IndexError) as e:
        raise ShapExplanationUnavailable(f"Could not extract a base estimator from the calibrated model: {e}")

    background = _background_sample()

    if model_name == "logistic_regression":
        scaler = base_estimator.named_steps["scaler"]
        clf = base_estimator.named_steps["clf"]
        background_transformed = scaler.transform(background[FEATURE_COLUMNS])
        X_transformed = scaler.transform(X_row[FEATURE_COLUMNS])
        explainer = shap.LinearExplainer(clf, background_transformed)
        shap_values = explainer(X_transformed)
        values = shap_values.values[0]
        base_value = float(shap_values.base_values[0])
    else:  # random_forest, xgboost
        explainer = shap.TreeExplainer(base_estimator)
        shap_values = explainer(X_row[FEATURE_COLUMNS])
        values = shap_values.values[0]
        base_values = shap_values.base_values[0]
        if hasattr(values, "ndim") and values.ndim == 2:
            # Binary classifier with a per-class axis (e.g. random_forest) --
            # take the positive class (index 1).
            values = values[:, 1]
            base_value = float(base_values[1]) if hasattr(base_values, "__len__") else float(base_values)
        else:
            base_value = float(base_values)

    return {
        "shap_values": {feature: round(float(v), 5) for feature, v in zip(FEATURE_COLUMNS, values)},
        "base_value": round(base_value, 5),
        "output_space": OUTPUT_SPACE_BY_MODEL[model_name],
        "model_name": model_name,
    }
