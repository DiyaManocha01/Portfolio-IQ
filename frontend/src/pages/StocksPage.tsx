import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAsync } from '../hooks/useAsync';
import * as stockService from '../services/stocks';
import { Card } from '../components/Card';
import { ErrorBlock, LoadingBlock, EmptyBlock } from '../components/States';

export default function StocksPage() {
  const stocks = useAsync(() => stockService.getStocks(), []);
  const [query, setQuery] = useState('');

  const filtered = useMemo(() => {
    if (!stocks.data) return [];
    const q = query.trim().toLowerCase();
    if (!q) return stocks.data;
    return stocks.data.filter(
      (s) => s.symbol.toLowerCase().includes(q) || s.name.toLowerCase().includes(q) || s.sector.toLowerCase().includes(q)
    );
  }, [stocks.data, query]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Stocks</h1>
          <p className="mt-1 text-sm text-slate-400">Browse the full universe of tracked stocks.</p>
        </div>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search symbol, name, or sector…"
          className="w-full rounded-lg border border-base-border bg-base-surface2 px-3 py-2.5 text-sm text-slate-100 placeholder-slate-600 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 sm:w-72"
        />
      </div>

      {stocks.loading && <LoadingBlock />}
      {stocks.error && <ErrorBlock message={stocks.error} onRetry={stocks.reload} />}
      {stocks.data && filtered.length === 0 && (
        <EmptyBlock title="No stocks match your search" message="Try a different symbol, company name, or sector." />
      )}

      {filtered.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((s) => (
            <Link key={s.symbol} to={`/stocks/${s.symbol}`}>
              <Card className="h-full transition hover:border-brand-500/50 hover:shadow-lg">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-lg font-bold text-slate-100">{s.symbol}</p>
                    <p className="text-xs text-slate-400">{s.name}</p>
                  </div>
                  <span className="rounded-full border border-base-border bg-base-surface2 px-2 py-0.5 text-[10px] font-medium text-slate-400">
                    {s.exchange}
                  </span>
                </div>
                <div className="mt-4 flex items-center justify-between text-xs text-slate-500">
                  <span>{s.sector}</span>
                  <span>{s.industry}</span>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
