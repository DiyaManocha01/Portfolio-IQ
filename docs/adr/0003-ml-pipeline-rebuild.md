# ADR 0003: Rebuild the ML Training Pipeline (Phase 6)

**Status:** Accepted
**Date:** 2026-10-21

## Context

The Phase 1-3 MVP training pipeline (`app/ml/train.py`) used a single
chronological 70/15/15 split per stock, no probability calibration, and
reported only the selected model's own accuracy/AUC with no baseline
comparison. ADR 0001 flagged this as scheduled for supersession once
Phase 6 was implemented.

## Decision

Rebuilt `app/ml/train.py` and `app/ml/predict.py`:

1. **Purged walk-forward cross-validation** (`app/ml/features.py::purged_walk_forward_splits`)
   replaces the single split: 5 expanding-window folds per stock, with an
   embargo (= the 1-day label horizon) purging any training row whose
   label window overlaps the start of that fold's test block. Candidates
   are ranked by mean validation ROC-AUC across all folds, not a single
   validation score.
2. **The winning model type is calibrated** via `CalibratedClassifierCV`
   (Platt/sigmoid scaling, chosen over isotonic given our modest per-fold
   sample sizes) and a reliability diagram is saved
   (`app/data/models/calibration_plot.png`, gitignored, regenerated every
   training run).
3. **Two baselines are always computed on the same held-out test set**:
   majority-class (predicts the training set's most common label) and
   momentum (predicts the sign of the prior day's return, scored by that
   return's magnitude for AUC). Both are stored in `model_metadata.json`
   next to the real model's metrics, so an accuracy number is never
   reported without this context -- on the current synthetic data, the
   selected model (0.545 test AUC) only modestly beats both baselines
   (0.519 and 0.5), which is itself informative and is not hidden.
4. **`model_version`** is now a 12-character hash of the methodology
   (feature list, split params, calibration method, selected model type),
   not an arbitrary counter -- it changes automatically if any of those
   change, and is stored on every `predictions` row (new nullable column,
   migration `0002_add_model_version_to_predictions.py`) so a prediction
   can always be traced to the exact methodology that produced it.
5. Logistic regression is now a `Pipeline(StandardScaler, LogisticRegression)`
   rather than a hand-managed separate scaler artifact -- this was also a
   minor correctness fix: scaling now happens inside each internal CV fold
   (both the walk-forward folds and `CalibratedClassifierCV`'s internal
   folds) rather than being fit once outside them, removing a theoretical
   (if minor, given the previous split was strictly train-then-val-then-test)
   leakage path. `predict.py` no longer loads or needs a separate scaler
   file.

## Consequences

- `app/ml/features.py::time_aware_split` is kept (unused by the main
  pipeline now) as a documented, still-correct utility rather than deleted
  -- no other code references it, but removing a working function that
  costs nothing to keep seemed unnecessary.
- `docs/limitations.md` gains an entry: `CalibratedClassifierCV`'s internal
  calibration folds are NOT time-aware (a known scikit-learn limitation for
  this use case) -- a fully rigorous implementation would need a custom
  purged calibration split, which is out of scope for this phase.
- Reported accuracy/AUC numbers remain close to random (as before Phase 6)
  -- this rebuild is about methodology rigor (no leakage, honest baselines,
  calibrated probabilities), not about making the synthetic data more
  predictable, which it cannot do.

## Alternatives considered

- **Isotonic calibration instead of Platt/sigmoid.** Rejected for now:
  isotonic regression is non-parametric and prone to overfitting on the
  small per-fold sample sizes here (a few hundred rows); sigmoid's
  parametric form is more stable at this scale. Revisit once training runs
  on the full real NIFTY 100 cache (Phase 4), which will have far more data.
- **A true nested/purged calibration split.** Would be more rigorous but
  adds meaningful complexity for a pipeline still running on synthetic
  data; deferred, documented as a known limitation rather than silently
  accepted as if it weren't a simplification.
