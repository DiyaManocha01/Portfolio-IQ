# ADR 0006: Per-Prediction SHAP Explanations (Phase 17)

**Status:** Accepted
**Date:** 2026-10-21

## Context

Phase 6's `PredictionService.predict_for_stock()` set `important_features`
to the top 3 entries of `model_metadata.json`'s `feature_importance_rank`
-- a single, static ranking computed ONCE at training time from the
winning model's global coefficients/feature importances
(`train.py::train_and_select_model`). Every stock's prediction showed the
SAME three "important features," regardless of that specific stock's
actual feature values. This was flagged in the original 23-phase roadmap
as scheduled for supersession by Phase 17 (SHAP explanations).

## Decision

1. **`important_features` is now derived per-prediction**, from a real
   SHAP (SHapley Additive exPlanations) decomposition of THIS stock's
   current feature row, not the training-run-wide ranking. Verified to
   actually differ between stocks (e.g. TCS vs. INFY order their top-3
   features differently) -- not just a relabeling of the same static list.
2. **Fast, model-type-specific exact explainers**, not the generic
   `shap.Explainer`: `shap.LinearExplainer` for `logistic_regression` (on
   the scaler-transformed feature space), `shap.TreeExplainer` for
   `random_forest`/`xgboost`. Measured at single-digit milliseconds vs.
   ~7.5 seconds for the generic permutation-based explainer against this
   project's actual models -- a real, measured engineering decision, not
   an assumption.
3. **SHAP explains the UNCALIBRATED base estimator**
   (`calibrated_classifiers_[0].estimator`), not the calibrated model
   actually served. Calibration (Phase 6) is a monotonic 1-D remapping,
   so it doesn't change which features matter or their direction, but
   `base_value + sum(shap_values)` reconstructs the base estimator's raw
   log-odds/score, NOT the exact calibrated probability actually served
   -- verified directly (`0.2559` from SHAP vs. `0.2559` from
   `math.log(p/(1-p))` on the base estimator's own `predict_proba`, an
   exact match; the calibrated model's served probability is a different,
   separately-computed number).
4. **A pooled background sample is saved during training**
   (`shap_background.joblib`, gitignored like other model artifacts),
   tied to the exact same training run's data as the deployed model --
   not a separately-curated reference set that could drift out of sync.
5. **Graceful degradation, not a hard failure**: if SHAP explanation
   isn't available (missing background sample, an older model artifact
   predating this phase, an unrecognized model type), `predict_for_stock()`
   falls back to the old static `feature_importance_rank` rather than
   failing the prediction entirely -- a prediction without its
   explanation is still useful; a 503 over a missing explanation would not
   be.
6. **No database schema change.** The full per-feature SHAP breakdown
   (`shap_values`, `base_value`, `output_space`) is computed fresh on
   every prediction request (cheap, see point 2) and attached as a
   transient (non-mapped) attribute on the returned `Prediction` ORM
   object for the API route to read -- never persisted, so no Alembic
   migration was needed for this phase.

## Consequences

- **SHAP output units differ by model type** -- `random_forest`'s
  TreeExplainer output is naturally in probability-contribution space (a
  random forest's leaves are themselves probability estimates), while
  `logistic_regression` and `xgboost` are in log-odds/margin space.
  Every explanation reports `output_space` explicitly; comparing raw SHAP
  magnitudes across model types without checking it would be wrong. See
  `docs/limitations.md`.
- `PredictionOut` gains three new optional fields
  (`shap_values`/`shap_base_value`/`shap_output_space`, all `None` when
  unavailable) -- additive, no existing field removed or renamed.
- New dependency `shap` (MIT) plus its transitive dependencies (`slicer`,
  `numba`, `llvmlite`, `tqdm` -- all permissive licenses, checked and
  recorded in `docs/open-source-inventory.md` in the same commit per
  rule 7).
- `docs/methodology.md` Section 14 documents the full methodology,
  including the exact verification numbers above.

## Alternatives considered

- **Explaining the calibrated model directly** (wrapping
  `CalibratedClassifierCV.predict_proba` in the generic `shap.Explainer`,
  as initially tried). Rejected: ~7.5 seconds per explanation is not
  viable for a request-time API call, and the calibration layer being
  monotonic means explaining the base estimator preserves everything
  that actually matters (feature ranking and direction) at a fraction of
  the cost.
- **Forcing probability-space output uniformly across all three model
  types** (via SHAP's interventional/probability-output mode for tree
  models, and a delta-method approximation for the linear model).
  Rejected for this phase: meaningfully slower and more complex, and the
  log-odds-vs-probability distinction is a well-understood, standard SHAP
  caveat that's more honest to document explicitly than to paper over
  with an approximation of unknown additional error.
