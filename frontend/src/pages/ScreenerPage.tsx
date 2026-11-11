import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAsync } from '../hooks/useAsync';
import * as stockService from '../services/stocks';
import * as screenerService from '../services/screener';
import { Card } from '../components/Card';
import { ErrorBlock, LoadingBlock, EmptyBlock } from '../components/States';
import { formatCurrency, formatNumber, formatSignedPct } from '../utils/format';
import type { ScreenerFilters, ScreenerResultOut } from '../types/api';

type FormState = { [K in keyof ScreenerFilters]?: string };

const NUMERIC_FIELDS: { key: keyof ScreenerFilters; label: string; placeholder?: string }[] = [
  { key: 'market_cap_min', label: 'Market Cap Min (₹)' },
  { key: 'market_cap_max', label: 'Market Cap Max (₹)' },
  { key: 'pe_min', label: 'P/E Min' },
  { key: 'pe_max', label: 'P/E Max' },
  { key: 'roe_min', label: 'ROE Min (%)', placeholder: 'e.g. 0.15 = 15%' },
  { key: 'debt_to_equity_max', label: 'Debt/Equity Max' },
  { key: 'dividend_yield_min', label: 'Dividend Yield Min (%)' },
  { key: 'revenue_growth_min', label: 'Revenue Growth Min', placeholder: 'e.g. 0.1 = 10%' },
  { key: 'profit_growth_min', label: 'Profit Growth Min', placeholder: 'e.g. 0.1 = 10%' },
  { key: 'rsi_min', label: 'RSI Min' },
  { key: 'rsi_max', label: 'RSI Max' },
  { key: 'momentum_10d_min', label: '10d Momentum Min' },
];

function toFilters(form: FormState): ScreenerFilters {
  const filters: ScreenerFilters = {};
  if (form.sector) filters.sector = form.sector;
  for (const { key } of NUMERIC_FIELDS) {
    const raw = form[key];
    if (raw !== undefined && raw !== '') {
      const num = Number(raw);
      if (!Number.isNaN(num)) (filters as Record<string, number>)[key] = num;
    }
  }
  return filters;
}

export default function ScreenerPage() {
  const stocks = useAsync(() => stockService.getStocks(), []);
  const [form, setForm] = useState<FormState>({});
  const [appliedFilters, setAppliedFilters] = useState<ScreenerFilters>({});

  const screener = useAsync(() => screenerService.runScreener(appliedFilters), [appliedFilters]);

  const sectors = useMemo(() => {
    if (!stocks.data) return [];
    return Array.from(new Set(stocks.data.map((s) => s.sector))).sort();
  }, [stocks.data]);

  function handleApply(e: React.FormEvent) {
    e.preventDefault();
    setAppliedFilters(toFilters(form));
  }

  function handleReset() {
    setForm({});
    setAppliedFilters({});
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Screener</h1>
        <p className="mt-1 text-sm text-slate-400">
          Filter the tracked universe by fundamentals and technical indicators. This is not a recommendation to buy
          or sell any stock.
        </p>
      </div>

      <Card title="Filters">
        <form onSubmit={handleApply} className="space-y-4">
          <div>
            <label htmlFor="screener-sector" className="mb-1 block text-xs font-medium text-slate-400">
              Sector
            </label>
            <select
              id="screener-sector"
              value={form.sector ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, sector: e.target.value || undefined }))}
              className="w-full rounded-lg border border-base-border bg-base-surface2 px-3 py-2 text-sm text-slate-100 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 sm:w-72"
            >
              <option value="">All sectors</option>
              {sectors.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {NUMERIC_FIELDS.map(({ key, label, placeholder }) => (
              <div key={key}>
                <label htmlFor={`screener-${key}`} className="mb-1 block text-xs font-medium text-slate-400">
                  {label}
                </label>
                <input
                  id={`screener-${key}`}
                  type="number"
                  step="any"
                  value={form[key] ?? ''}
                  placeholder={placeholder}
                  onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                  className="w-full rounded-lg border border-base-border bg-base-surface2 px-3 py-2 text-sm text-slate-100 placeholder-slate-600 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
                />
              </div>
            ))}
          </div>

          <div className="flex gap-3">
            <button
              type="submit"
              className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-500 transition"
            >
              Apply Filters
            </button>
            <button
              type="button"
              onClick={handleReset}
              className="rounded-lg border border-base-border px-4 py-2 text-sm font-medium text-slate-300 hover:bg-base-surface2 transition"
            >
              Reset
            </button>
          </div>
        </form>
      </Card>

      {screener.loading && <LoadingBlock label="Running screener…" />}
      {screener.error && <ErrorBlock message={screener.error} onRetry={screener.reload} />}
      {screener.data && screener.data.count === 0 && (
        <EmptyBlock title="No matches" message="No stocks in the tracked universe match these filters." />
      )}
      {screener.data && screener.data.count > 0 && <ResultsTable results={screener.data.results} />}
    </div>
  );
}

function ResultsTable({ results }: { results: ScreenerResultOut[] }) {
  return (
    <Card title={`${results.length} match${results.length === 1 ? '' : 'es'}`}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px] text-left text-sm">
          <thead>
            <tr className="border-b border-base-border text-xs uppercase tracking-wide text-slate-500">
              <th className="py-2 pr-4">Symbol</th>
              <th className="py-2 pr-4">Sector</th>
              <th className="py-2 pr-4 text-right">Price</th>
              <th className="py-2 pr-4 text-right">Market Cap</th>
              <th className="py-2 pr-4 text-right">P/E</th>
              <th className="py-2 pr-4 text-right">ROE</th>
              <th className="py-2 pr-4 text-right">Div. Yield</th>
              <th className="py-2 pr-4 text-right">Revenue Gr.</th>
              <th className="py-2 pr-4 text-right">RSI</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-base-border">
            {results.map((r) => (
              <tr key={r.symbol} className="hover:bg-base-surface2/50">
                <td className="py-2.5 pr-4">
                  <Link to={`/stocks/${r.symbol}`} className="font-semibold text-slate-100 hover:text-brand-300">
                    {r.symbol}
                  </Link>
                </td>
                <td className="py-2.5 pr-4 text-slate-400">{r.sector}</td>
                <td className="py-2.5 pr-4 text-right text-slate-200">{formatCurrency(r.current_price)}</td>
                <td className="py-2.5 pr-4 text-right text-slate-200">{formatCurrency(r.market_cap, { compact: true })}</td>
                <td className="py-2.5 pr-4 text-right text-slate-200">{formatNumber(r.pe_ratio, 1)}</td>
                <td className="py-2.5 pr-4 text-right text-slate-200">{r.roe !== null ? `${(r.roe * 100).toFixed(1)}%` : '—'}</td>
                <td className="py-2.5 pr-4 text-right text-slate-200">{r.dividend_yield !== null ? `${r.dividend_yield.toFixed(2)}%` : '—'}</td>
                <td className="py-2.5 pr-4 text-right">
                  {r.revenue_growth_yoy !== null ? formatSignedPct(r.revenue_growth_yoy * 100) : '—'}
                </td>
                <td className="py-2.5 pr-4 text-right text-slate-200">{formatNumber(r.rsi_14, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
