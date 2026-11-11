# ADR 0011: Paper Trading (Phase 28)

**Status:** Accepted
**Date:** 2026-11-11

## Context

Phase 28 asked for a hypothetical trading account: virtual starting
cash, simulated buy/sell transactions at real (or dev-sample) market
prices, virtual holdings, transaction history, portfolio valuation,
unrealized/realized P&L, performance tracking, and a benchmark
comparison -- with no real order execution or brokerage integration,
and every transaction clearly identified as hypothetical. The CLAUDE.md
rule that nothing here may ever mutate the real portfolio is the same
constraint the Phase 11 What-If Simulator already had to satisfy.

## Decision

### Wholly separate tables, not a flag on the real ones

`PaperAccount` / `PaperHolding` / `PaperTransaction`
(`app/models/paper_trading.py`) are new tables, never touching the real
`Portfolio` / `Holding` / `Transaction` tables. A "simulate" flag on the
real tables would have been fewer lines of schema, but it would mean
every existing portfolio query (risk, health, fit, what-if, stress test)
would need to start filtering it out correctly forever -- one missed
filter anywhere and a hypothetical trade leaks into a real metric. Two
separate families of tables make that leak structurally impossible
instead of a discipline to maintain, the same tradeoff the What-If
Simulator already made for its own hypothetical state.

### Reuses existing pricing and cost-estimation code, invents neither

- Execution prices come from `MarketDataService.get_quote` -- the same
  real-or-dev-sample price every other feature uses, never invented.
- Fees reuse `estimate_indian_trade_cost`
  (`app/portfolio/whatif_service.py`, Phase 11's illustrative,
  honesty-flagged NSE delivery-trade cost model: STT, stamp duty,
  exchange charges, SEBI fee, GST, zero brokerage default) instead of
  defining a second, slightly-different cost formula for the same kind
  of trade.
- The performance series (`get_performance`) reuses the same
  documented simplification as the real portfolio's
  `portfolio_calc.py::get_performance_series()`: current holding
  quantities are assumed constant across the lookback window, not
  reconstructed trade-by-trade. Inventing a more elaborate (even if
  more accurate) methodology just for the paper account would leave two
  different, inconsistent answers to "what does a performance chart
  mean" in the same codebase.
- The benchmark/"strategy comparison" requirement is interpreted as
  NIFTY 50 bought-and-held with the same starting cash over the same
  window (normalized via `starting_cash * price / price_at_window_start`),
  nothing more elaborate invented.

### `total_pnl` is `total_value - starting_cash`, not `unrealized + realized`

A buy's fees debit cash immediately but are never folded into
`avg_buy_price`/`invested_value`, so they don't show up in
`unrealized_pnl` until the position is sold. Summing the two
per-trade-type P&L figures would therefore silently under-count total
loss by exactly the fees paid on positions still open. `get_valuation`
instead defines `total_pnl = total_value - starting_cash`, which is
always correct by construction; `unrealized_pnl` and `realized_pnl`
are still reported separately as price-only figures for transparency,
and are documented as not summing to `total_pnl` while any fee-bearing
position remains open -- that gap is the unpaid fee drag, not a bug.
This was caught while writing `test_valuation_totals_are_consistent`,
before it shipped.

### Reset is a destructive action, allowed here specifically because it's hypothetical

`POST /paper-trading/account/reset` deletes all holdings and
transactions and restores starting cash. This would be an alarming
capability on the real portfolio; it is safe and expected on a
sandbox account whose entire purpose is "try something, then start
over."

## Consequences

- One Alembic migration (`a1f36418e47d`): `paper_accounts`,
  `paper_holdings`, `paper_transactions`. The `type` column reuses the
  existing `transaction_type` Postgres enum via
  `postgresql.ENUM(..., create_type=False)` -- autogenerate's default
  `sa.Enum(..., create_type=False)` did not suppress the `CREATE TYPE`
  statement and failed with `DuplicateObject` on a type that already
  exists from an earlier migration; the dialect-specific form was
  needed instead.
- No new dependencies.
- 20 new backend tests cover cost-basis averaging, insufficient
  cash/holding errors, realized P&L on partial sells, the `total_pnl`
  consistency fix, performance/benchmark series, and user isolation.
- Every account response carries a `disclaimer` field naming it
  hypothetical, per CLAUDE.md's rule that outputs stay framed as
  simulations, never real trading activity.
- **Not verified beyond this sandbox's synthetic/dev-sample data**: no
  simulated trade has executed against a real market price, since this
  environment has no live feed (see docs/limitations.md and the
  existing Phase 24/26/27 ADRs for why).
