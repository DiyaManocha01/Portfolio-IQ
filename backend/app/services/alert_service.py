"""Phase 27: evaluates AlertRules and creates AlertEvents.

Reuses existing calculation code only -- nothing here recomputes a
metric a service already owns:
  - price/volume/RSI: app/services/analytics.py + MarketDataService
  - sentiment: app/services/news_service.py's get_sentiment_summary
  - portfolio volatility / sector concentration: app/portfolio/risk_service.py
  - Fit Engine score: app/portfolio/fit_service.py

Dedup ("avoid excessive notifications," required by Phase 27's scope):
  - PRICE_THRESHOLD / RSI_THRESHOLD ("crossing" types): fire only when the
    metric actually crosses the threshold between this evaluation and the
    last one (comparing against AlertRule.last_value), never while it
    merely continues to sit above/below it.
  - PRICE_PCT_MOVE / VOLUME_SPIKE (already-a-delta-today metrics): fire at
    most once per calendar day, since "today's move" is inherently a
    daily concept -- re-firing every evaluation tick while the market
    stays volatile would be exactly the noise this requirement warns
    against.
  - SENTIMENT_CHANGE / PORTFOLIO_VOLATILITY_CHANGE /
    SECTOR_CONCENTRATION_CHANGE / FIT_RANKING_CHANGE ("change since last
    check" types): fire only once the metric has moved by a full
    `threshold`-sized step from the value last fired on, then rebaseline
    to the new value -- so the next alert needs another full move, not a
    reset to zero.
  - A blanket 60-second cooldown on every rule is the last safety net
    against overlapping evaluations (the Phase 24 background loop and a
    manual POST /alerts/evaluate could otherwise race).
  - A rule's very first evaluation ever only establishes a baseline
    (`last_value`) and never fires -- there is nothing to have "changed"
    or "crossed" from yet.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.models.alert import AlertDirection, AlertEvent, AlertRule, AlertRuleType
from app.models.portfolio import Portfolio
from app.models.stock import Stock
from app.services import analytics
from app.services.market_data.service import MarketDataService
from app.services.news_service import NewsService

COOLDOWN_SECONDS = 60


def _now() -> dt.datetime:
    return dt.datetime.now(tz=dt.timezone.utc)


def _eval_price_threshold(db: Session, rule: AlertRule) -> tuple[float, str] | None:
    market_data = MarketDataService(db)
    latest, _ = market_data.get_quote(rule.stock)
    message = f"{rule.stock.symbol} crossed {rule.direction.value.lower()} ₹{rule.threshold:.2f} (now ₹{latest.close:.2f})"
    return latest.close, message


def _eval_price_pct_move(db: Session, rule: AlertRule) -> tuple[float, str] | None:
    market_data = MarketDataService(db)
    latest, previous = market_data.get_quote(rule.stock)
    if previous is None or previous.close == 0:
        return None
    pct_move = (latest.close - previous.close) / previous.close * 100
    message = f"{rule.stock.symbol} moved {pct_move:+.2f}% today (threshold: {rule.threshold:.2f}%)"
    return pct_move, message


def _eval_volume_spike(db: Session, rule: AlertRule) -> tuple[float, str] | None:
    market_data = MarketDataService(db)
    history = market_data.get_history(rule.stock, days=30)
    if len(history) < 10:
        return None
    df = analytics.ohlcv_to_frame(history)
    avg_vol = analytics.avg_volume(df["volume"], 20).iloc[-1]
    if not avg_vol:
        return None
    latest_volume = df["volume"].iloc[-1]
    ratio = latest_volume / avg_vol
    message = f"{rule.stock.symbol} volume is {ratio:.1f}x its 20-day average (threshold: {rule.threshold:.1f}x)"
    return float(ratio), message


def _eval_rsi_threshold(db: Session, rule: AlertRule) -> tuple[float, str] | None:
    market_data = MarketDataService(db)
    history = market_data.get_history(rule.stock, days=60)
    if len(history) < 15:
        return None
    df = analytics.ohlcv_to_frame(history)
    rsi_value = analytics.rsi(df["close"], 14).iloc[-1]
    if rsi_value is None:
        return None
    message = f"{rule.stock.symbol} RSI(14) crossed {rule.direction.value.lower()} {rule.threshold:.1f} (now {float(rsi_value):.1f})"
    return float(rsi_value), message


def _eval_sentiment_change(db: Session, rule: AlertRule) -> tuple[float, str] | None:
    summary = NewsService(db).get_sentiment_summary(rule.stock)
    current = summary["average_score_time_decayed"]
    delta = current - (rule.last_value if rule.last_value is not None else current)
    message = f"{rule.stock.symbol} sentiment score shifted by {delta:+.3f} since the last check (now {current:.3f})"
    return current, message


def _get_user_portfolio(db: Session, user_id: int) -> Portfolio | None:
    return db.query(Portfolio).filter(Portfolio.user_id == user_id).first()


def _eval_portfolio_volatility_change(db: Session, rule: AlertRule) -> tuple[float, str] | None:
    from app.portfolio.risk_service import PortfolioRiskService

    portfolio = _get_user_portfolio(db, rule.user_id)
    if portfolio is None or not list(portfolio.holdings):
        return None
    result = PortfolioRiskService(db).compute(portfolio)
    current = result["annualized_volatility"] * 100
    delta = current - (rule.last_value if rule.last_value is not None else current)
    message = f"Portfolio annualized volatility shifted by {delta:+.2f} percentage points since the last check (now {current:.2f}%)"
    return current, message


def _eval_sector_concentration_change(db: Session, rule: AlertRule) -> tuple[float, str] | None:
    from app.portfolio.risk_service import PortfolioRiskService

    portfolio = _get_user_portfolio(db, rule.user_id)
    if portfolio is None or not list(portfolio.holdings):
        return None
    result = PortfolioRiskService(db).compute(portfolio)
    sector_concentration = result["sector_concentration"]
    if not sector_concentration:
        return None
    current = max(sc["pct"] for sc in sector_concentration)
    delta = current - (rule.last_value if rule.last_value is not None else current)
    message = f"Largest sector concentration shifted by {delta:+.2f} percentage points since the last check (now {current:.2f}%)"
    return current, message


def _eval_fit_ranking_change(db: Session, rule: AlertRule) -> tuple[float, str] | None:
    from app.portfolio.fit_service import PortfolioFitService, default_preset_for

    portfolio = _get_user_portfolio(db, rule.user_id)
    if portfolio is None:
        return None
    preset = default_preset_for(portfolio)
    fit = PortfolioFitService(db, preset=preset).compute_fit(rule.stock, portfolio)
    current = fit["fit_score"]
    delta = current - (rule.last_value if rule.last_value is not None else current)
    message = f"{rule.stock.symbol}'s Portfolio Fit score shifted by {delta:+.1f} points since the last check (now {current:.1f})"
    return current, message


_EVALUATORS = {
    AlertRuleType.PRICE_THRESHOLD: _eval_price_threshold,
    AlertRuleType.PRICE_PCT_MOVE: _eval_price_pct_move,
    AlertRuleType.VOLUME_SPIKE: _eval_volume_spike,
    AlertRuleType.RSI_THRESHOLD: _eval_rsi_threshold,
    AlertRuleType.SENTIMENT_CHANGE: _eval_sentiment_change,
    AlertRuleType.PORTFOLIO_VOLATILITY_CHANGE: _eval_portfolio_volatility_change,
    AlertRuleType.SECTOR_CONCENTRATION_CHANGE: _eval_sector_concentration_change,
    AlertRuleType.FIT_RANKING_CHANGE: _eval_fit_ranking_change,
}

_CROSSING_TYPES = {AlertRuleType.PRICE_THRESHOLD, AlertRuleType.RSI_THRESHOLD}
_DAILY_TYPES = {AlertRuleType.PRICE_PCT_MOVE, AlertRuleType.VOLUME_SPIKE}


def _crossed(previous: float, current: float, threshold: float, direction: AlertDirection) -> bool:
    if direction == AlertDirection.ABOVE:
        return previous <= threshold < current
    return previous >= threshold > current


def _should_fire(rule: AlertRule, current_value: float, now: dt.datetime) -> bool:
    if rule.last_value is None:
        return False  # first-ever evaluation only establishes a baseline

    if rule.last_fired_at is not None and (now - rule.last_fired_at).total_seconds() < COOLDOWN_SECONDS:
        return False

    if rule.rule_type in _CROSSING_TYPES:
        return _crossed(rule.last_value, current_value, rule.threshold, rule.direction)

    if rule.rule_type in _DAILY_TYPES:
        if abs(current_value) < rule.threshold:
            return False
        return rule.last_fired_at is None or rule.last_fired_at.date() != now.date()

    # "change since last check" types: fire once a full threshold-sized
    # step has accumulated since the value last fired on (or since the
    # baseline, if it has never fired).
    reference = rule.last_value
    return abs(current_value - reference) >= rule.threshold


def evaluate_rule(db: Session, rule: AlertRule) -> AlertEvent | None:
    """Evaluates one rule, updates its dedup state, and returns a new
    AlertEvent if (and only if) it should fire. Returns None otherwise --
    including when the underlying data isn't available yet (e.g. a
    portfolio with no holdings), in which case the rule's state is left
    untouched rather than guessed at.
    """
    if not rule.enabled:
        return None

    evaluator = _EVALUATORS[rule.rule_type]
    result = evaluator(db, rule)
    if result is None:
        return None
    current_value, message = result

    now = _now()
    fire = _should_fire(rule, current_value, now)

    event = None
    if fire:
        event = AlertEvent(rule_id=rule.id, triggered_at=now, value=current_value, message=message)
        db.add(event)
        rule.last_fired_at = now

    # Crossing/daily types need last_value refreshed every tick to detect
    # the *next* crossing or day boundary. Delta ("change since last
    # check") types deliberately only rebaseline on an actual fire (or on
    # the very first evaluation) -- otherwise comparing against the
    # immediately-prior tick would hide a genuine slow drift that never
    # crosses the threshold in any single evaluation interval.
    if rule.rule_type in _CROSSING_TYPES or rule.rule_type in _DAILY_TYPES or rule.last_value is None or fire:
        rule.last_value = current_value
    rule.last_evaluated_at = now
    db.commit()
    if event is not None:
        db.refresh(event)
    return event


def evaluate_rules(db: Session, rules: list[AlertRule]) -> list[AlertEvent]:
    events = []
    for rule in rules:
        try:
            event = evaluate_rule(db, rule)
        except Exception:  # noqa: BLE001 -- one bad rule shouldn't block the rest
            db.rollback()
            continue
        if event is not None:
            events.append(event)
    return events
