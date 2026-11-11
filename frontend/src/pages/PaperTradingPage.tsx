import { FormEvent, useState } from 'react';
import clsx from 'clsx';
import { useAsync } from '../hooks/useAsync';
import * as paperTradingService from '../services/paperTrading';
import { Card } from '../components/Card';
import { DataSourceBadge } from '../components/Badge';
import { ErrorBlock, LoadingBlock, EmptyBlock } from '../components/States';
import { PaperPerformanceChart } from '../charts/PaperPerformanceChart';
import { getErrorMessage } from '../services/api';
import { formatCurrency, formatDateTime, formatNumber, formatSignedPct } from '../utils/format';
import type { PaperHoldingOut } from '../types/api';

export default function PaperTradingPage() {
  const account = useAsync(() => paperTradingService.getAccount(), []);
  const transactions = useAsync(() => paperTradingService.listTransactions(), []);
  const performance = useAsync(() => paperTradingService.getPerformance(180), []);

  const [symbol, setSymbol] = useState('');
  const [quantity, setQuantity] = useState('');
  const [submitting, setSubmitting] = useState<'BUY' | 'SELL' | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);

  function reloadAll() {
    account.reload();
    transactions.reload();
    performance.reload();
  }

  async function handleTrade(side: 'BUY' | 'SELL') {
    setFormError(null);
    const qty = Number(quantity);
    if (!symbol) {
      setFormError('Enter a stock symbol.');
      return;
    }
    if (!qty || qty <= 0) {
      setFormError('Quantity must be a positive number.');
      return;
    }
    setSubmitting(side);
    try {
      const payload = { symbol: symbol.toUpperCase(), quantity: qty };
      if (side === 'BUY') await paperTradingService.buy(payload);
      else await paperTradingService.sell(payload);
      setQuantity('');
      reloadAll();
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setSubmitting(null);
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    handleTrade('BUY');
  }

  async function handleReset() {
    setResetting(true);
    try {
      await paperTradingService.resetAccount();
      reloadAll();
    } finally {
      setResetting(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Paper Trading</h1>
          <p className="mt-1 text-sm text-slate-400">
            A hypothetical account funded with virtual cash. Trades execute at real (or dev-sample) market prices,
            but no real money, orders, or brokerage integration is involved.
          </p>
        </div>
        <button
          onClick={handleReset}
          disabled={resetting}
          className="shrink-0 rounded-lg border border-base-border px-4 py-2 text-sm font-medium text-slate-400 hover:border-negative/40 hover:text-negative transition disabled:opacity-50"
        >
          {resetting ? 'Resetting…' : 'Reset Account'}
        </button>
      </div>

      {account.loading && <LoadingBlock />}
      {account.error && <ErrorBlock message={account.error} onRetry={account.reload} />}

      {account.data && (
        <>
          <div className="rounded-lg border border-base-border bg-base-surface2 px-4 py-2.5 text-xs text-slate-400">
            {account.data.disclaimer}
          </div>

          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <SummaryTile label="Cash Balance" value={formatCurrency(account.data.cash_balance)} />
            <SummaryTile label="Holdings Value" value={formatCurrency(account.data.holdings_value)} />
            <SummaryTile label="Total Value" value={formatCurrency(account.data.total_value)} />
            <SummaryTile
              label="Total P&L"
              value={formatCurrency(account.data.total_pnl)}
              sub={formatSignedPct(account.data.total_return_pct)}
              positive={account.data.total_pnl >= 0}
            />
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <Card title="Holdings" className="lg:col-span-2" action={<DataSourceBadge source={account.data.data_source} />}>
              {account.data.holdings.length === 0 && (
                <EmptyBlock title="No holdings yet" message="Use the form to place your first simulated trade." />
              )}
              {account.data.holdings.length > 0 && <PaperHoldingsTable holdings={account.data.holdings} />}
            </Card>

            <Card title="Buy / Sell">
              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-400">Symbol</label>
                  <input
                    value={symbol}
                    onChange={(e) => setSymbol(e.target.value)}
                    placeholder="e.g. TCS"
                    className="w-full rounded-lg border border-base-border bg-base-surface2 px-3 py-2.5 text-sm text-slate-100 placeholder-slate-600 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-400">Quantity</label>
                  <input
                    type="number"
                    min="0"
                    step="any"
                    value={quantity}
                    onChange={(e) => setQuantity(e.target.value)}
                    placeholder="e.g. 10"
                    className="w-full rounded-lg border border-base-border bg-base-surface2 px-3 py-2.5 text-sm text-slate-100 placeholder-slate-600 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
                  />
                </div>

                {formError && (
                  <div className="rounded-lg border border-negative/30 bg-negative-bg px-3 py-2 text-xs text-negative">{formError}</div>
                )}

                <div className="flex gap-3">
                  <button
                    type="submit"
                    disabled={submitting !== null}
                    className="flex-1 rounded-lg bg-brand-600 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-60"
                  >
                    {submitting === 'BUY' ? 'Buying…' : 'Buy'}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleTrade('SELL')}
                    disabled={submitting !== null}
                    className="flex-1 rounded-lg border border-negative/40 py-2.5 text-sm font-semibold text-negative transition hover:bg-negative/10 disabled:opacity-60"
                  >
                    {submitting === 'SELL' ? 'Selling…' : 'Sell'}
                  </button>
                </div>
                <p className="text-[11px] text-slate-500">
                  Fees are estimated using the same illustrative NSE delivery-trade cost model used by the What-If
                  Simulator.
                </p>
              </form>
            </Card>
          </div>

          <Card title="Performance vs. NIFTY 50">
            {performance.loading && <LoadingBlock />}
            {performance.error && <ErrorBlock message={performance.error} onRetry={performance.reload} />}
            {performance.data && performance.data.points.length === 0 && (
              <EmptyBlock title="No performance history yet" message="Place a trade to start tracking account value over time." />
            )}
            {performance.data && performance.data.points.length > 0 && (
              <>
                <div className="mb-4 flex gap-6 text-sm">
                  <div>
                    <span className="text-slate-500">Account return: </span>
                    <span className={performance.data.account_return_pct >= 0 ? 'text-positive' : 'text-negative'}>
                      {formatSignedPct(performance.data.account_return_pct)}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500">NIFTY 50 return: </span>
                    <span className={performance.data.benchmark_return_pct >= 0 ? 'text-positive' : 'text-negative'}>
                      {formatSignedPct(performance.data.benchmark_return_pct)}
                    </span>
                  </div>
                </div>
                <PaperPerformanceChart performance={performance.data} />
              </>
            )}
          </Card>

          <Card title="Transaction History">
            {transactions.loading && <LoadingBlock />}
            {transactions.error && <ErrorBlock message={transactions.error} onRetry={transactions.reload} />}
            {transactions.data && transactions.data.length === 0 && (
              <EmptyBlock title="No transactions yet" message="Your simulated buy/sell history will show up here." />
            )}
            {transactions.data && transactions.data.length > 0 && (
              <ul className="divide-y divide-base-border">
                {transactions.data.map((t) => (
                  <li key={t.id} className="flex items-center justify-between gap-4 py-3 text-sm">
                    <div className="min-w-0">
                      <p className="text-slate-100">
                        <span className={clsx('mr-2 font-semibold', t.type === 'BUY' ? 'text-brand-300' : 'text-negative')}>
                          {t.type}
                        </span>
                        {formatNumber(t.quantity)} {t.symbol} @ {formatCurrency(t.price)}
                      </p>
                      <p className="mt-0.5 text-xs text-slate-500">
                        Fees: {formatCurrency(t.fees)} · {formatDateTime(t.executed_at)}
                        {t.realized_pnl !== null && (
                          <>
                            {' '}
                            · Realized P&amp;L:{' '}
                            <span className={t.realized_pnl >= 0 ? 'text-positive' : 'text-negative'}>
                              {formatCurrency(t.realized_pnl)}
                            </span>
                          </>
                        )}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}
    </div>
  );
}

function SummaryTile({ label, value, sub, positive }: { label: string; value: string; sub?: string; positive?: boolean }) {
  return (
    <div className="rounded-xl border border-base-border bg-base-surface p-4">
      <p className="text-xs text-slate-500">{label}</p>
      <p className={clsx('mt-1 text-lg font-semibold', positive === undefined ? 'text-slate-100' : positive ? 'text-positive' : 'text-negative')}>
        {value}
      </p>
      {sub && <p className={clsx('text-xs', positive ? 'text-positive' : 'text-negative')}>{sub}</p>}
    </div>
  );
}

function PaperHoldingsTable({ holdings }: { holdings: PaperHoldingOut[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] text-xs sm:text-sm">
        <thead>
          <tr className="border-b border-base-border text-left text-[10px] sm:text-xs uppercase tracking-wide text-slate-500">
            <th className="py-2 pr-2 font-medium">Stock</th>
            <th className="py-2 pr-2 font-medium text-right">Qty</th>
            <th className="py-2 pr-2 font-medium text-right">Avg Buy</th>
            <th className="py-2 pr-2 font-medium text-right">Price</th>
            <th className="py-2 pr-2 font-medium text-right">Value</th>
            <th className="py-2 pr-2 font-medium text-right">Unrealized P&amp;L</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-base-border">
          {holdings.map((h) => {
            const positive = h.unrealized_pnl >= 0;
            return (
              <tr key={h.symbol} className="hover:bg-base-surface2/60 transition">
                <td className="py-2.5 pr-2">
                  <div className="font-semibold text-slate-100">{h.symbol}</div>
                  <div className="hidden text-[11px] text-slate-500 sm:block">{h.name}</div>
                </td>
                <td className="py-2.5 pr-2 text-right text-slate-300">{formatNumber(h.quantity)}</td>
                <td className="py-2.5 pr-2 text-right text-slate-300 whitespace-nowrap">{formatCurrency(h.avg_buy_price)}</td>
                <td className="py-2.5 pr-2 text-right text-slate-300 whitespace-nowrap">{formatCurrency(h.current_price)}</td>
                <td className="py-2.5 pr-2 text-right font-medium text-slate-100 whitespace-nowrap">{formatCurrency(h.current_value)}</td>
                <td className={clsx('py-2.5 pr-2 text-right font-medium whitespace-nowrap', positive ? 'text-positive' : 'text-negative')}>
                  {formatCurrency(h.unrealized_pnl)} ({formatSignedPct(h.unrealized_pnl_pct)})
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
