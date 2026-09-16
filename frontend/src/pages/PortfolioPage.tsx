import { FormEvent, useState } from 'react';
import { useAsync } from '../hooks/useAsync';
import * as portfolioService from '../services/portfolio';
import * as stockService from '../services/stocks';
import { Card } from '../components/Card';
import { HoldingsTable } from '../components/HoldingsTable';
import { ErrorBlock, LoadingBlock, EmptyBlock } from '../components/States';
import { getErrorMessage } from '../services/api';
import type { Holding } from '../types/api';

export default function PortfolioPage() {
  const holdings = useAsync(() => portfolioService.getHoldings(), []);
  const stocks = useAsync(() => stockService.getStocks(), []);

  const [symbol, setSymbol] = useState('');
  const [quantity, setQuantity] = useState('');
  const [avgPrice, setAvgPrice] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);
  const [removingId, setRemovingId] = useState<number | null>(null);

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
    </div>
  );
}
