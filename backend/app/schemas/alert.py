from datetime import datetime

from pydantic import BaseModel, model_validator

from app.models.alert import AlertDirection, AlertRuleType

_STOCK_SCOPED_TYPES = {
    AlertRuleType.PRICE_THRESHOLD,
    AlertRuleType.PRICE_PCT_MOVE,
    AlertRuleType.VOLUME_SPIKE,
    AlertRuleType.RSI_THRESHOLD,
    AlertRuleType.SENTIMENT_CHANGE,
    AlertRuleType.FIT_RANKING_CHANGE,
}
_DIRECTIONAL_TYPES = {AlertRuleType.PRICE_THRESHOLD, AlertRuleType.RSI_THRESHOLD}


class AlertRuleCreate(BaseModel):
    rule_type: AlertRuleType
    symbol: str | None = None
    direction: AlertDirection | None = None
    threshold: float

    @model_validator(mode="after")
    def _validate_shape(self) -> "AlertRuleCreate":
        if self.rule_type in _STOCK_SCOPED_TYPES and not self.symbol:
            raise ValueError(f"{self.rule_type.value} requires a symbol")
        if self.rule_type not in _STOCK_SCOPED_TYPES and self.symbol:
            raise ValueError(f"{self.rule_type.value} is portfolio-level and must not set a symbol")
        if self.rule_type in _DIRECTIONAL_TYPES and self.direction is None:
            raise ValueError(f"{self.rule_type.value} requires a direction (ABOVE or BELOW)")
        if self.rule_type not in _DIRECTIONAL_TYPES and self.direction is not None:
            raise ValueError(f"{self.rule_type.value} does not use a direction -- its threshold is a magnitude")
        if self.threshold <= 0 and self.rule_type not in _DIRECTIONAL_TYPES:
            raise ValueError("threshold must be positive for a magnitude-based rule")
        return self


class AlertRuleUpdate(BaseModel):
    enabled: bool | None = None
    threshold: float | None = None


class AlertRuleOut(BaseModel):
    id: int
    rule_type: AlertRuleType
    symbol: str | None
    direction: AlertDirection | None
    threshold: float
    enabled: bool
    last_value: float | None
    last_evaluated_at: datetime | None
    last_fired_at: datetime | None
    created_at: datetime


class AlertEventOut(BaseModel):
    id: int
    rule_id: int
    rule_type: AlertRuleType
    symbol: str | None
    triggered_at: datetime
    value: float
    message: str
    is_read: bool
