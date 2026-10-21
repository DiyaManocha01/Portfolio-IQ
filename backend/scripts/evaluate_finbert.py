#!/usr/bin/env python3
"""Compare FinBERT vs. the lexicon sentiment scorer on real headlines (Phase 7).

Run this LOCALLY, on a machine with internet access to huggingface.co (to
download ProsusAI/finbert on first run) -- this sandbox cannot reach that
host (verified, same restriction documented throughout this project), so
this script has never actually been executed here, and no numbers from it
appear anywhere else in this repo as if they had been measured.

Usage:
    cd backend
    source venv/bin/activate
    pip install transformers torch   # not in requirements.txt by default --
                                       # see docs/open-source-inventory.md
    python scripts/evaluate_finbert.py

What this does and does NOT measure:
    - There is no human-labeled ground-truth sentiment dataset for these
      headlines in this project. This script therefore measures AGREEMENT
      between FinBERT and the lexicon scorer (how often they produce the
      same label), NOT accuracy against a correct answer. Reporting this
      as "accuracy" would be a false claim -- it isn't.
    - Prefers real headlines from the RSS cache (app/services/news/cache.py,
      populated by scripts/fetch_news_rss.py) if present. Falls back to the
      synthetic template headlines otherwise, WITH A LOUD WARNING, since
      agreement measured on templated text (which was partly written using
      the same positive/negative word choices the lexicon scorer looks for)
      is close to meaningless as an evaluation of either model.

Known limitation this script exists partly to document (see also
docs/limitations.md): FinBERT (ProsusAI/finbert) was trained on English
financial text -- primarily Reuters TRC2 and the Financial PhraseBank
corpus, both Western/US-centric sources. Indian financial English
headlines (ET/Moneycontrol) are in English and share financial
terminology, so FinBERT should transfer reasonably -- but India-specific
terms (SEBI, RBI, GST, specific Indian corporate structures), code-mixed
Hindi-English phrasing sometimes seen in regional business press, and
India-specific events/context are NOT represented in FinBERT's training
data. This script's agreement-rate output is a rough signal for this, not
a rigorous NLP evaluation -- a proper one needs human-labeled Indian
financial headlines, which does not exist in this project.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.nlp import finbert_sentiment, lexicon_sentiment
from app.services.news import cache as rss_cache

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "finbert_eval_results.csv"


def _get_headlines() -> tuple[list[str], str]:
    real = rss_cache.read_cache()
    if real:
        return [h.headline for h in real], "real (RSS cache)"

    print(
        "WARNING: no real headline cache found (run scripts/fetch_news_rss.py "
        "first for a meaningful evaluation). Falling back to the synthetic "
        "template headlines -- agreement measured on these is NOT a "
        "meaningful FinBERT evaluation, only a smoke test that both scorers run.",
        file=sys.stderr,
    )
    from app.services.news_service import HEADLINE_TEMPLATES

    return [t.format(name="[Company]") for t, _bias in HEADLINE_TEMPLATES], "synthetic (fallback, not a real evaluation)"


def main():
    headlines, source_label = _get_headlines()
    print(f"Evaluating {len(headlines)} headlines from: {source_label}\n")

    rows = []
    agree = 0
    for headline in headlines:
        lex_score = lexicon_sentiment.score_text(headline)
        lex_label = lexicon_sentiment.label_for_score(lex_score)

        try:
            fb_score, fb_label = finbert_sentiment.score_text(headline)
        except Exception as e:  # noqa: BLE001 -- report and continue; a single bad row shouldn't abort the run
            print(f"  [FinBERT error on headline, skipping] {e}")
            continue

        matches = lex_label == fb_label
        agree += int(matches)
        rows.append(
            {
                "headline": headline,
                "lexicon_label": lex_label,
                "lexicon_score": round(lex_score, 3),
                "finbert_label": fb_label,
                "finbert_score": round(fb_score, 3),
                "agree": matches,
            }
        )

    if not rows:
        print("No rows produced -- nothing to report.")
        return

    agreement_rate = agree / len(rows)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Lexicon/FinBERT label agreement: {agreement_rate:.1%} over {len(rows)} headlines")
    print(f"(This is agreement between two unsupervised scorers, NOT accuracy against ground truth -- see this file's docstring.)")
    print(f"Full results written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
