from app.config import settings
from app.nlp import lexicon_sentiment


class SentimentService:
    """Pipeline: headline text -> sentiment label + score.

    Selects between the FinBERT provider and the lexicon fallback based on
    ``settings.USE_FINBERT``. Both providers implement the same
    (score, label) contract so the rest of the app is agnostic to which one
    is active.
    """

    def __init__(self):
        self.use_finbert = settings.USE_FINBERT
        self.model_name = "finbert" if self.use_finbert else "lexicon-v1"

    def analyze(self, text: str) -> tuple[str, float]:
        """Returns (label, score) where score is in [-1, 1]."""
        if self.use_finbert:
            from app.nlp import finbert_sentiment

            score, label = finbert_sentiment.score_text(text)
            return label, score

        score = lexicon_sentiment.score_text(text)
        label = lexicon_sentiment.label_for_score(score)
        return label, score
