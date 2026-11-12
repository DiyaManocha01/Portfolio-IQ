# ADR 0014: Real-Portfolio Transaction Ledger + Advanced Performance (Phase 31)

**Status:** Accepted
**Date:** 2026-11-12

## Context

Phase 31 asked for daily/cumulative returns, a benchmark comparison,
drawdown, historical volatility, risk-adjusted performance, sector- and
holding-level contribution, a performance timeline, a clear realised-vs-
unrealised distinction, and correct handling of corporate actions
(splits/dividends).

Auditing the codebase surfaced a real gap: the real portfolio has never
had a transaction flow. `POST /portfolio/holdings` sets a holding's
quantity/avg price directly; `DELETE /portfolio/holdings/{id}` removes
one outright. The `Transaction` model has existed since the original
schema but was never populated for the real portfolio (only `Paper
Trading`, Phase 28, uses the `TransactionType` enum it defines). With no
sell flow, there was nothing to compute a "realised P&L" from --
reporting one would mean either fabricating history (CLAUDE.md rule 5)
or silently always showing zero with no explanation. This was raised
with the project owner directly; the decision was to add real
transaction logging rather than ship "unrealised only."

## Decision

### Transaction logging is additive, not a backfill

`POST /portfolio/holdings` now also inserts a `Transaction(type=BUY)` row
alongside the existing holding create/merge logic (unchanged). A new
`POST /portfolio/holdings/{id}/sell` (price, optional quantity) reduces
or removes the holding and inserts a `Transaction(type=SELL,
realized_pnl=(price - avg_buy_price) * quantity)`. `GET
/portfolio/transactions` lists them newest-first. Holdings that already
existed before this phase, or that are removed via the untouched
`DELETE /portfolio/holdings/{id}`, have no transaction history --
**never backfilled**, per CLAUDE.md rule 5. This is documented as a real
limitation, not quietly smoothed over.

### `DELETE` and `/sell` stay two different operations

`DELETE /portfolio/holdings/{id}` keeps its original behavior exactly:
remove a holding, no price, no transaction, no realized P&L -- for
correcting a mis-entered holding. `/sell` is new and distinct: it
requires a price, computes and logs realized P&L, and is what a user
reaches for to record an actual sale. Collapsing these into one
endpoint would have forced every `DELETE` caller to suddenly supply a
price or accept a fabricated one.

### No fee/cost model on real-portfolio sells

Unlike Paper Trading (Phase 28), which reuses the Phase 11 Indian
brokerage-cost model for its simulated trades, real-portfolio
`realized_pnl` here is pure price difference: `(price - avg_buy_price)
* quantity`. Phase 31's spec asks for a realised/unrealised distinction,
not a cost model, and the real portfolio has never modeled fees
anywhere else (`HoldingCreate` has no fee field either) -- adding one
only to the sell path would be an inconsistent, unasked-for addition.

### Advanced performance reuses existing calculations rather than re-deriving them

`app/portfolio/portfolio_performance_service.py` composes, rather than
recomputes:
- `portfolio_calc.get_performance_series()` for the value-over-time
  series (unchanged, same "current holdings held constant" simplification
  already documented there).
- `PortfolioRiskService.compute()` (Phase 8) already reports
  `annualized_volatility`, `sharpe_ratio`, and `max_drawdown` at
  `/portfolio/risk` -- this phase does not duplicate that endpoint.
  `portfolio_performance_service` additionally reports
  `annualized_volatility_realized`, computed directly from the
  performance series' own realized daily returns (a second, independently
  derived volatility figure, useful as a cross-check against Phase 8's
  holdings-return-based one -- the two can differ since they're computed
  from different underlying return series).

New in this phase: a NIFTY 50 buy-and-hold benchmark series (same
normalization approach as Paper Trading's Phase 28 benchmark -- nothing
more elaborate, not a backtested strategy); a running drawdown *series*
(Phase 8 only ever reported the single worst value); and sector-/
holding-level contribution to total unrealized P&L (each holding's/
sector's P&L as a percentage of total P&L -- distinct from Phase 14's
risk-attribution, which allocates portfolio *risk*, not *return*,
across holdings).

A new `GET /portfolio/performance/advanced` endpoint carries all of
this, rather than extending the existing `GET /portfolio/performance`
in place -- the same precedent as Phase 14 adding `/risk-attribution`
alongside `/risk` instead of growing one response indefinitely.

### Corporate actions: already handled via the data source, not new logic

`LiveYFinanceProvider.get_history` now passes `auto_adjust=True`
explicitly to `yfinance`'s `Ticker.history()` (previously relying on the
library's own default). This means the OHLC yfinance returns is already
split- and dividend-adjusted -- a 2:1 split does not appear as a 50%
price drop in any return/drawdown/volatility calculation downstream, with
no separate correction logic needed or written. `DevSampleProvider`'s
synthetic random walk has no corporate actions to adjust for in the
first place. No new code path exists for "handling" corporate actions
beyond this one explicit flag and this documentation.

## Consequences

- One Alembic migration (`25b450765c4c`): adds `transactions.realized_pnl`
  (nullable, populated for SELL only).
- No new dependencies.
- 16 new backend tests (transaction logging via buy/sell/delete routes,
  realized P&L correctness, contribution sums, drawdown/cumulative-return
  sanity checks, benchmark normalization) plus 2 new and 2 updated
  frontend tests.
- **Realized P&L will read as 0 for every portfolio until a sale happens
  through the new `/sell` endpoint.** This is correct, not a bug --
  there is no real sale to report yet for any pre-existing holding.
- **Not verified beyond this sandbox's synthetic/dev-sample data**: no
  sell has ever executed against a real market price, and the
  `auto_adjust=True` corporate-action handling has never been exercised
  against a real stock that actually underwent a split or paid a
  dividend in this environment, since this sandbox has no live feed
  (see docs/limitations.md and the existing Phase 4/24/28 ADRs for why).
