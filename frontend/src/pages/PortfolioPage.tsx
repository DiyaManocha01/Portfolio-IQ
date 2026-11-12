import { FormEvent, useState } from 'react';
import { useAsync } from '../hooks/useAsync';
import * as portfolioService from '../services/portfolio';
import * as stockService from '../services/stocks';
import { Card } from '../components/Card';
import { HoldingsTable } from '../components/HoldingsTable';
import { ErrorBlock, LoadingBlock, EmptyBlock } from '../components/States';
import { getErrorMessage } from '../services/api';
import { formatCurrency, formatDate, formatNumber } from '../utils/format';
import type { Holding } from '../types/api';

export default function PortfolioPage() {
  const holdings = useAsync(() => portfolioService.getHoldings(), []);
  const stocks = useAsync(() => stockService.getStocks(), []);
  const transactions = useAsync(() => portfolioService.listTransactions(), []);

  const [symbol, setSymbol] = useState('');
  const [quantity, setQuantity] = useState('');
  const [avgPrice, setAvgPrice] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);
  const [removingId, setRemovingId] = useState<number | null>(null);

  const [sellHoldingId, setSellHoldingId] = useState('');
  const [sellPrice, setSellPrice] = useState('');
  const [sellQuantity, setSellQuantity] = useState('');
  const [sellSubmitting, setSellSubmitting] = useState(false);
  const [sellError, setSellError] = useState<string | null>(null);
  const [sellSuccess, setSellSuccess] = useState<string | null>(null);

  async function handleAdd(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    setFormSuccess(null);
    const qty = Number(quantity);
    const price = Number(avgPrice);
    if (!symbol) {
      setFormError('Please choose a stock symbol.');
      return;
    }
    if (!qty || qty <= 0) {
      setFormError('Quantity must be a positive number.');
      return;
    }
    if (!price || price <= 0) {
      setFormError('Average buy price must be a positive number.');
      return;
    }
    setSubmitting(true);
    try {
      await portfolioService.addHolding(symbol, qty, price);
      setFormSuccess(`Added ${qty} shares of ${symbol}.`);
      setSymbol('');
      setQuantity('');
      setAvgPrice('');
      holdings.reload();
      transactions.reload();
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRemove(h: Holding) {
    setRemovingId(h.id);
    try {
      await portfolioService.removeHolding(h.id);
      holdings.reload();
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setRemovingId(null);
    }
  }

  async function handleSell(e: FormEvent) {
    e.preventDefault();
    setSellError(null);
    setSellSuccess(null);
    const holdingId = Number(sellHoldingId);
    const price = Number(sellPrice);
    if (!holdingId) {
      setSellError('Please choose a holding to sell.');
      return;
    }
    if (!price || price <= 0) {
      setSellError('Sell price must be a positive number.');
      return;
    }
    const quantity = sellQuantity.trim() ? Number(sellQuantity) : undefined;
    if (quantity !== undefined && quantity <= 0) {
      setSellError('Quantity must be a positive number, or left blank to sell the entire position.');
      return;
    }
    setSellSubmitting(true);
    try {
      const txn = await portfolioService.sellHolding(holdingId, { price, quantity });
      setSellSuccess(`Sold ${txn.quantity} shares of ${txn.symbol} -- realized P&L ${formatCurrency(txn.realized_pnl)}.`);
      setSellHoldingId('');
      setSellPrice('');
      setSellQuantity('');
      holdings.reload();
      transactions.reload();
    } catch (err) {
      setSellError(getErrorMessage(err));
    } finally {
      setSellSubmitting(false);
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">My Portfolio</h1>
        <p className="mt-1 text-sm text-slate-400">Manage your holdings — figures are computed server-side from live quotes.</p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card title="Holdings" className="lg:col-span-2">
          {holdings.loading && <LoadingBlock />}
          {holdings.error && <ErrorBlock message={holdings.error} onRetry={holdings.reload} />}
          {holdings.data && holdings.data.length > 0 && (
            <HoldingsTable holdings={holdings.data} onRemove={handleRemove} removing={removingId} />
          )}
          {holdings.data && holdings.data.length === 0 && (
            <EmptyBlock title="No holdings yet" message="Use the form to add your first stock position." />
          )}
        </Card>

        <Card title="Add Stock">
          <form onSubmit={handleAdd} className="space-y-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-400">Symbol</label>
              {stocks.loading && <div className="text-xs text-slate-500">Loading stock list…</div>}
              {stocks.error && <div className="text-xs text-negative">{stocks.error}</div>}
              {stocks.data && (
                <select
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                  className="w-full rounded-lg border border-base-border bg-base-surface2 px-3 py-2.5 text-sm text-slate-100 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
                >
                  <option value="">Select a stock…</option>
                  {stocks.data.map((s) => (
                    <option key={s.symbol} value={s.symbol}>
                      {s.symbol} — {s.name}
                    </option>
                  ))}
                </select>
              )}
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-400">Quantity</label>
              <input
                type="number"
                min="0"
                step="any"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                className="w-full rounded-lg border border-base-border bg-base-surface2 px-3 py-2.5 text-sm text-slate-100 placeholder-slate-600 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
                placeholder="e.g. 10"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-400">Average Buy Price (₹)</label>
              <input
                type="number"
                min="0"
                step="any"
                value={avgPrice}
                onChange={(e) => setAvgPrice(e.target.value)}
                className="w-full rounded-lg border border-base-border bg-base-surface2 px-3 py-2.5 text-sm text-slate-100 placeholder-slate-600 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
                placeholder="e.g. 3200"
              />
            </div>

            {formError && (
              <div className="rounded-lg border border-negative/30 bg-negative-bg px-3 py-2 text-xs text-negative">{formError}</div>
            )}
            {formSuccess && (
              <div className="rounded-lg border border-positive/30 bg-positive-bg px-3 py-2 text-xs text-positive">{formSuccess}</div>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-lg bg-brand-600 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-60"
            >
              {submitting ? 'Adding…' : 'Add to Portfolio'}
            </button>
            <p className="text-[11px] text-slate-500">
              Adding a symbol you already hold merges into a weighted-average position.
            </p>
          </form>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card title="Sell a Holding" subtitle="Logs a transaction with realized P&L -- distinct from Remove, which deletes without recording a sale" className="lg:col-span-1">
          <form onSubmit={handleSell} className="space-y-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-400">Holding</label>
              {holdings.data && (
                <select
                  value={sellHoldingId}
                  onChange={(e) => setSellHoldingId(e.target.value)}
                  className="w-full rounded-lg border border-base-border bg-base-surface2 px-3 py-2.5 text-sm text-slate-100 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
                >
                  <option value="">Select a holding…</option>
                  {holdings.data.map((h) => (
                    <option key={h.id} value={h.id}>
                      {h.symbol} ({formatNumber(h.quantity)} shares)
                    </option>
                  ))}
                </select>
              )}
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-400">Sell Price (₹)</label>
              <input
                type="number"
                min="0"
                step="any"
                value={sellPrice}
                onChange={(e) => setSellPrice(e.target.value)}
                className="w-full rounded-lg border border-base-border bg-base-surface2 px-3 py-2.5 text-sm text-slate-100 placeholder-slate-600 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
                placeholder="e.g. 3600"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-400">Quantity (optional)</label>
              <input
                type="number"
                min="0"
                step="any"
                value={sellQuantity}
                onChange={(e) => setSellQuantity(e.target.value)}
                className="w-full rounded-lg border border-base-border bg-base-surface2 px-3 py-2.5 text-sm text-slate-100 placeholder-slate-600 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
                placeholder="Leave blank to sell the entire position"
              />
            </div>

            {sellError && (
              <div className="rounded-lg border border-negative/30 bg-negative-bg px-3 py-2 text-xs text-negative">{sellError}</div>
            )}
            {sellSuccess && (
              <div className="rounded-lg border border-positive/30 bg-positive-bg px-3 py-2 text-xs text-positive">{sellSuccess}</div>
            )}

            <button
              type="submit"
              disabled={sellSubmitting}
              className="w-full rounded-lg border border-negative/40 py-2.5 text-sm font-semibold text-negative transition hover:bg-negative/10 disabled:opacity-60"
            >
              {sellSubmitting ? 'Selling…' : 'Sell'}
            </button>
          </form>
        </Card>

        <Card title="Transaction History" className="lg:col-span-2">
          {transactions.loading && <LoadingBlock />}
          {transactions.error && <ErrorBlock message={transactions.error} onRetry={transactions.reload} />}
          {transactions.data && transactions.data.length === 0 && (
            <EmptyBlock
              title="No transactions yet"
              message="Buying or selling a holding logs a transaction here. Holdings added before this feature shipped have no history."
            />
          )}
          {transactions.data && transactions.data.length > 0 && (
            <ul className="divide-y divide-base-border">
              {transactions.data.map((t) => (
                <li key={t.id} className="flex items-center justify-between gap-4 py-3 text-sm">
                  <div className="min-w-0">
                    <p className="text-slate-100">
                      <span className={t.type === 'BUY' ? 'mr-2 font-semibold text-brand-300' : 'mr-2 font-semibold text-negative'}>
                        {t.type}
                      </span>
                      {formatNumber(t.quantity)} {t.symbol} @ {formatCurrency(t.price)}
                    </p>
                    <p className="mt-0.5 text-xs text-slate-500">
                      {formatDate(t.transaction_date)}
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
      </div>
    </div>
  );
}
