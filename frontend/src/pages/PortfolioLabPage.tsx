import { useState } from 'react';
import clsx from 'clsx';
import { useAsync } from '../hooks/useAsync';
import * as portfolioService from '../services/portfolio';
import * as stockService from '../services/stocks';
import { Card } from '../components/Card';
import { StatCard } from '../components/StatCard';
import { ErrorBlock, LoadingBlock } from '../components/States';
import { DataSourceBadge } from '../components/Badge';
import { HorizontalBarChart } from '../charts/HorizontalBarChart';
import { colorForIndex } from '../charts/palette';
import { getErrorMessage } from '../services/api';
import { formatCurrency, formatNumber, formatProbabilityPct, formatSignedPct } from '../utils/format';
import type { OptimizationMethod, PortfolioOptimization, WhatIfChange, WhatIfResult } from '../types/api';

type Tab = 'whatif' | 'optimize';

export default function PortfolioLabPage() {
  const [tab, setTab] = useState<Tab>('whatif');

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Portfolio Lab</h1>
        <p className="mt-1 text-sm text-slate-400">
          Hypothetical simulations. Nothing here changes your real holdings unless you separately add/remove them on
          the Portfolio page.
        </p>
      </div>

      <div className="flex gap-2 border-b border-base-border">
        {(
          [
            { id: 'whatif', label: 'What-If Simulator' },
            { id: 'optimize', label: 'Optimization' },
          ] as const
        ).map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={clsx(
              'px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition',
              tab === t.id ? 'border-brand-500 text-brand-300' : 'border-transparent text-slate-400 hover:text-slate-200'
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'whatif' ? <WhatIfTab /> : <OptimizeTab />}
    </div>
  );
}

function WhatIfTab() {
  const holdings = useAsync(() => portfolioService.getHoldings(), []);
  const stocks = useAsync(() => stockService.getStocks(), []);

  const [quantities, setQuantities] = useState<Record<string, string>>({});
  const [newSymbol, setNewSymbol] = useState('');
  const [newQuantity, setNewQuantity] = useState('');
  const [includeCosts, setIncludeCosts] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [result, setResult] = useState<WhatIfResult | null>(null);

  async function handleSimulate() {
    if (!holdings.data) return;
    setFormError(null);

    const changes: WhatIfChange[] = [];
    for (const h of holdings.data) {
      const raw = quantities[h.symbol];
      if (raw === undefined || raw === '') continue;
      const qty = Number(raw);
      if (Number.isNaN(qty) || qty < 0) {
        setFormError(`Invalid new quantity for ${h.symbol}.`);
        return;
      }
      if (qty !== h.quantity) changes.push({ symbol: h.symbol, new_quantity: qty });
    }
    if (newSymbol && newQuantity) {
      const qty = Number(newQuantity);
      if (Number.isNaN(qty) || qty <= 0) {
        setFormError('New position quantity must be a positive number.');
        return;
      }
      changes.push({ symbol: newSymbol, new_quantity: qty });
    }
    if (changes.length === 0) {
      setFormError('Change at least one quantity, or add a new position, before simulating.');
      return;
    }

    setSubmitting(true);
    try {
      const r = await portfolioService.postWhatIf(changes, includeCosts);
      setResult(r);
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  const heldSymbols = new Set((holdings.data ?? []).map((h) => h.symbol));

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <Card title="Hypothetical Changes" className="lg:col-span-1">
        {holdings.loading && <LoadingBlock />}
        {holdings.error && <ErrorBlock message={holdings.error} onRetry={holdings.reload} />}
        {holdings.data && (
          <div className="space-y-3">
            {holdings.data.map((h) => (
              <div key={h.id} className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-slate-100">{h.symbol}</p>
                  <p className="text-xs text-slate-500">currently {formatNumber(h.quantity, 2)}</p>
                </div>
                <input
                  type="number"
                  min="0"
                  step="any"
                  placeholder={String(h.quantity)}
                  value={quantities[h.symbol] ?? ''}
                  onChange={(e) => setQuantities((q) => ({ ...q, [h.symbol]: e.target.value }))}
                  className="w-24 rounded-lg border border-base-border bg-base-surface2 px-2.5 py-1.5 text-right text-sm text-slate-100 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
                />
              </div>
            ))}

            <div className="border-t border-base-border pt-3">
              <p className="mb-2 text-xs font-medium text-slate-400">Add a new hypothetical position</p>
              <div className="flex gap-2">
                {stocks.data && (
                  <select
                    value={newSymbol}
                    onChange={(e) => setNewSymbol(e.target.value)}
                    className="min-w-0 flex-1 rounded-lg border border-base-border bg-base-surface2 px-2 py-1.5 text-xs text-slate-100 outline-none focus:border-brand-500"
                  >
                    <option value="">Select…</option>
                    {stocks.data
                      .filter((s) => !heldSymbols.has(s.symbol))
                      .map((s) => (
                        <option key={s.symbol} value={s.symbol}>
                          {s.symbol}
                        </option>
                      ))}
                  </select>
                )}
                <input
                  type="number"
                  min="0"
                  step="any"
                  placeholder="qty"
                  value={newQuantity}
                  onChange={(e) => setNewQuantity(e.target.value)}
                  className="w-20 rounded-lg border border-base-border bg-base-surface2 px-2 py-1.5 text-right text-xs text-slate-100 outline-none focus:border-brand-500"
                />
              </div>
            </div>

            <label className="flex items-center gap-2 text-xs text-slate-400">
              <input type="checkbox" checked={includeCosts} onChange={(e) => setIncludeCosts(e.target.checked)} />
              Estimate Indian transaction costs
            </label>

            {formError && (
              <div className="rounded-lg border border-negative/30 bg-negative-bg px-3 py-2 text-xs text-negative">{formError}</div>
            )}

            <button
              onClick={handleSimulate}
              disabled={submitting}
              className="w-full rounded-lg bg-brand-600 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-60"
            >
              {submitting ? 'Simulating…' : 'Simulate'}
            </button>
          </div>
        )}
      </Card>

      <div className="space-y-6 lg:col-span-2">
        {result && (
          <>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <StatCard
                label="Volatility (before → after)"
                value={`${formatProbabilityPct(result.before.annualized_volatility)} → ${formatProbabilityPct(result.after.annualized_volatility)}`}
              />
              <StatCard
                label="Sharpe (before → after)"
                value={`${formatNumber(result.before.sharpe_ratio, 2)} → ${formatNumber(result.after.sharpe_ratio, 2)}`}
              />
              <StatCard
                label="Diversification Ratio"
                value={`${formatNumber(result.before.diversification_ratio, 2)} → ${formatNumber(result.after.diversification_ratio, 2)}`}
              />
              <StatCard
                label="Est. Transaction Cost"
                value={result.total_estimated_cost !== null ? formatCurrency(result.total_estimated_cost) : '—'}
                sub={<DataSourceBadge source={result.data_source} />}
              />
            </div>

            <Card title="Trades" subtitle="What would actually execute, hypothetically">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[480px] text-sm">
                  <thead>
                    <tr className="border-b border-base-border text-left text-xs uppercase tracking-wide text-slate-500">
                      <th className="pb-2 pr-3 font-medium">Symbol</th>
                      <th className="pb-2 pr-3 font-medium">Action</th>
                      <th className="pb-2 pr-3 font-medium text-right">Qty Δ</th>
                      <th className="pb-2 pr-3 font-medium text-right">Value</th>
                      <th className="pb-2 pr-3 font-medium text-right">Est. Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.trades.map((t) => (
                      <tr key={t.symbol} className="border-b border-base-border/60 last:border-0">
                        <td className="py-2.5 pr-3 font-semibold text-slate-100">{t.symbol}</td>
                        <td className={`py-2.5 pr-3 ${t.action === 'buy' ? 'text-positive' : 'text-negative'}`}>
                          {t.action.toUpperCase()}
                        </td>
                        <td className="py-2.5 pr-3 text-right text-slate-300">{formatSignedPct(t.quantity_delta, 2).replace('%', '')}</td>
                        <td className="py-2.5 pr-3 text-right text-slate-300">{formatCurrency(t.trade_value)}</td>
                        <td className="py-2.5 pr-3 text-right text-slate-400">
                          {t.estimated_cost ? formatCurrency(t.estimated_cost.total) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>

            <p className="rounded-lg border border-base-border bg-base-surface2 px-3 py-2 text-xs text-slate-400">
              {result.disclaimer}
            </p>
          </>
        )}
        {!result && (
          <Card>
            <p className="text-sm text-slate-500">
              Change a quantity or add a new hypothetical position, then simulate to see the before/after impact.
            </p>
          </Card>
        )}
      </div>
    </div>
  );
}

function OptimizeTab() {
  const [method, setMethod] = useState<OptimizationMethod>('min_variance');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PortfolioOptimization | null>(null);

  async function handleRun() {
    setLoading(true);
    setError(null);
    try {
      const r = await portfolioService.getOptimization(method);
      setResult(r);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-400">Method</label>
            <select
              value={method}
              onChange={(e) => setMethod(e.target.value as OptimizationMethod)}
              className="rounded-lg border border-base-border bg-base-surface2 px-3 py-2 text-sm text-slate-100 outline-none focus:border-brand-500"
            >
              <option value="min_variance">Minimum Variance</option>
              <option value="max_sharpe">Maximum Sharpe</option>
              <option value="risk_parity">Risk Parity (HRP)</option>
            </select>
          </div>
          <button
            onClick={handleRun}
            disabled={loading}
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-60"
          >
            {loading ? 'Computing…' : 'Suggest Allocation'}
          </button>
        </div>
      </Card>

      {error && <ErrorBlock message={error} onRetry={handleRun} />}

      {result && !result.feasible && (
        <Card>
          <p className="text-sm text-warn">Not feasible: {result.note}</p>
        </Card>
      )}

      {result && result.feasible && (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <StatCard label="Expected Annual Return" value={formatProbabilityPct(result.expected_annual_return)} />
            <StatCard label="Expected Annual Volatility" value={formatProbabilityPct(result.expected_annual_volatility)} />
            <StatCard
              label="Expected Sharpe"
              value={formatNumber(result.expected_sharpe_ratio, 2)}
              sub={<DataSourceBadge source={result.data_source} />}
            />
          </div>

          <Card title="Suggested Allocation" subtitle="Current vs. suggested weight by holding">
            <HorizontalBarChart
              data={result.allocations.map((a, i) => ({
                label: a.symbol,
                value: a.suggested_weight_pct,
                color: colorForIndex(i),
              }))}
              valueFormatter={(v) => `${v.toFixed(1)}%`}
              height={Math.max(200, result.allocations.length * 38)}
            />
            <div className="mt-4 space-y-1.5">
              {result.allocations.map((a) => (
                <div key={a.symbol} className="flex items-center justify-between text-xs">
                  <span className="font-medium text-slate-200">{a.symbol}</span>
                  <span className="text-slate-400">
                    {formatNumber(a.current_weight_pct, 1)}% → {formatNumber(a.suggested_weight_pct, 1)}%
                    <span className={a.delta_pct >= 0 ? 'text-positive' : 'text-negative'}> ({formatSignedPct(a.delta_pct, 1)})</span>
                  </span>
                </div>
              ))}
            </div>
          </Card>

          <p className="rounded-lg border border-base-border bg-base-surface2 px-3 py-2 text-xs text-slate-400">
            {result.disclaimer}
          </p>
        </>
      )}
    </div>
  );
}
