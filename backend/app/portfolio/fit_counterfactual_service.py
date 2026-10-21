"""FitCounterfactualService: explains Fit Engine rankings (Phase 16).

Two related questions, both tractable because Phase 10's Fit score is
`sigmoid(logit)` where `logit = sum(sign[term] * weight[term] * z[term])`
is ADDITIVE across terms:

1. "Why did stock A rank above stock B?" -- `logit_A - logit_B` decomposes
   EXACTLY into the sum of each term's contribution difference. A clean,
   verifiable algebraic identity, not an approximation.
2. "What would need to change for this stock to rank higher?" -- a
   CETERIS-PARIBUS, SINGLE-TERM counterfactual: for each term in
   isolation, how much would that term's raw value need to move (holding
   every other term fixed) to close the entire gap to a target. This is
   deliberately NOT a joint/minimal-change search across all five terms
   simultaneously -- that is a genuinely different (and harder, unsolved
   here) optimization problem. Every result from this service says "if
   ONLY this term changed," never "the smallest overall change needed."

Both stocks/targets in a single call are evaluated against the SAME
z-scoring population (the full stock universe, via
PortfolioFitService.compute_fit()), so the two logits being compared are
directly comparable -- see Phase 10's own documented caveat that scores
computed against DIFFERENT populations (e.g. one via /discover's batch,
one via this full-universe comparison) are not comparable to each other.
"""

from __future__ import annotations

import math

from sqlalchemy.orm import Session

from app.models.portfolio import Portfolio
from app.models.stock import Stock
from app.portfolio.fit_service import TERM_DISPLAY_NAME, TERM_SIGN, PortfolioFitService, default_preset_for


def _logit_from_score(score: float) -> float:
    """Inverse of fit_service.sigmoid_score(): given a target 0-100 Fit
    score, the logit that would produce it."""
    if not (0 < score < 100):
        raise ValueError("target_score must be strictly between 0 and 100 (0 and 100 imply an infinite logit).")
    p = score / 100.0
    return math.log(p / (1 - p))


class FitCounterfactualService:
    def __init__(self, db: Session, preset: str | None = None):
        self.db = db
        self.preset = preset

    def _fit_service(self, portfolio: Portfolio) -> PortfolioFitService:
        chosen = self.preset or default_preset_for(portfolio)
        return PortfolioFitService(self.db, preset=chosen)

    def explain_ranking_gap(self, portfolio: Portfolio, stock_a: Stock, stock_b: Stock) -> dict:
        svc = self._fit_service(portfolio)
        fit_a = svc.compute_fit(stock_a, portfolio)
        fit_b = svc.compute_fit(stock_b, portfolio)
        weights = fit_a["weights_used"]

        term_deltas = []
        for term in weights:
            contribution_a = TERM_SIGN[term] * weights[term] * fit_a["_z_scores"][term]
            contribution_b = TERM_SIGN[term] * weights[term] * fit_b["_z_scores"][term]
            term_deltas.append(
                {
                    "term": term,
                    "name": TERM_DISPLAY_NAME[term],
                    "contribution_a": round(contribution_a, 4),
                    "contribution_b": round(contribution_b, 4),
                    "delta": round(contribution_a - contribution_b, 4),
                }
            )
        term_deltas.sort(key=lambda d: -abs(d["delta"]))

        return {
            "symbol_a": fit_a["symbol"],
            "symbol_b": fit_b["symbol"],
            "fit_score_a": fit_a["fit_score"],
            "fit_score_b": fit_b["fit_score"],
            "logit_gap": round(fit_a["_logit"] - fit_b["_logit"], 4),
            "term_deltas": term_deltas,
            "preset": fit_a["preset"],
            "note": (
                "term_deltas sum exactly to logit_gap (an algebraic identity, not an "
                "approximation) -- sorted by absolute contribution to the gap, largest first."
            ),
        }

    def what_would_improve_rank(
        self,
        portfolio: Portfolio,
        stock: Stock,
        target_stock: Stock | None = None,
        target_score: float | None = None,
    ) -> dict:
        if (target_stock is None) == (target_score is None):
            raise ValueError("Provide exactly one of target_stock or target_score.")

        svc = self._fit_service(portfolio)
        fit = svc.compute_fit(stock, portfolio)
        weights = fit["weights_used"]

        if target_stock is not None:
            target_fit = svc.compute_fit(target_stock, portfolio)
            target_logit = target_fit["_logit"]
            target_label = target_fit["symbol"]
        else:
            target_logit = _logit_from_score(target_score)
            target_label = f"a Fit score of {target_score}"

        gap = target_logit - fit["_logit"]
        if gap <= 0:
            return {
                "symbol": fit["symbol"],
                "fit_score": fit["fit_score"],
                "target": target_label,
                "already_meets_target": True,
                "term_scenarios": [],
                "note": f"{fit['symbol']} already meets or exceeds the target -- no change needed.",
            }

        scenarios = []
        for term, weight in weights.items():
            if weight == 0:
                continue
            required_z_delta = gap / (TERM_SIGN[term] * weight)
            term_std = fit["_term_std"][term]
            current_raw = fit["_raw"][term]
            if term_std > 1e-9:
                required_raw_delta = required_z_delta * term_std
                target_raw_value = round(current_raw + required_raw_delta, 4)
            else:
                required_raw_delta = None
                target_raw_value = None
            scenarios.append(
                {
                    "term": term,
                    "name": TERM_DISPLAY_NAME[term],
                    "current_raw_value": round(current_raw, 4),
                    "required_z_delta": round(required_z_delta, 4),
                    "required_raw_delta": round(required_raw_delta, 4) if required_raw_delta is not None else None,
                    "target_raw_value": target_raw_value,
                }
            )
        scenarios.sort(key=lambda s: abs(s["required_z_delta"]))

        return {
            "symbol": fit["symbol"],
            "fit_score": fit["fit_score"],
            "target": target_label,
            "already_meets_target": False,
            "term_scenarios": scenarios,
            "note": (
                "Each scenario is CETERIS PARIBUS -- 'if ONLY this term changed, holding every "
                "other term fixed, this is how much it would need to move to close the gap.' "
                "This is NOT a joint, minimal-change search across all terms simultaneously, and "
                "a required change being numerically small does not mean it is realistically easy "
                "to achieve -- see docs/limitations.md."
            ),
        }
