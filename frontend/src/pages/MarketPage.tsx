import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAsync } from '../hooks/useAsync';
import { useMarketFeed } from '../hooks/useMarketFeed';
import * as marketService from '../services/market';
import { Card } from '../components/Card';
import { ErrorBlock, LoadingBlock, EmptyBlock } from '../components/States';
import { FeedStatusBadge, MarketSessionBadge, TickStatusBadge } from '../components/Badge';
import { formatCurrency, formatSignedPct, formatVolume, timeAgo } from '../utils/format';
import type { TickOut } from '../types/api';

export default function MarketPage() {
  const initial = useAsync(() => marketService.getMarketStatus(), []);
  const feed = useMarketFeed();
  const [query, setQuery] = useState('');

  // Prefer the live WebSocket push once it has delivered anything; fall
  // back to the one-off REST snapshot so the page isn't empty on first
  // paint while the socket is still connecting.
  const status = feed.data ?? initial.data;
  const ticks = status?.ticks ?? [];

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return ticks;
    return ticks.filter((t) => t.symbol.toLowerCase().includes(q));
  }, [ticks, query]);

  const { gainers, losers } = useMemo(() => {
    const withChange = ticks.filter((t) => t.change_percent !== null);
    const sorted = [...withChange].sort((a, b) => (b.change_percent ?? 0) - (a.change_percent ?? 0));
    return { gainers: sorted.slice(0, 3), losers: sorted.slice(-3).reverse() };
  }, [ticks]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Market</h1>
          <p className="mt-1 text-sm text-slate-400">
            Real-time status for the Phase 24 NSE watchlist — see each card's badge for exactly how fresh that price is.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {status && <MarketSessionBadge status={status.market_status} />}
          {status && <FeedStatusBadge status={status.feed_status} />}
        </div>
      </div>

      {initial.loading && !status && <LoadingBlock label="Loading market status…" />}
      {initial.error && !status && <ErrorBlock message={initial.error} onRetry={initial.reload} />}

      {status && status.feed_status !== 'CONNECTED' && (
        <div className="rounded-lg border border-base-border bg-base-surface2 px-4 py-2.5 text-xs text-slate-400">
          No live broker connection is configured right now — prices below are honestly labeled{' '}
          <TickStatusBadge status="FIXTURE" /> or similar rather than shown as live.
        </div>
      )}

      {ticks.length === 0 && status && (
        <EmptyBlock
          title="No prices yet"
          message="The watchlist cache hasn't been populated yet — this fills in automatically within about 30 seconds of the backend starting."
        />
      )}

      {ticks.length > 0 && (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Card title="Top Gainers" subtitle="Largest positive % change in the watchlist">
              <MoversList moves={gainers} />
            </Card>
            <Card title="Top Losers" subtitle="Largest negative % change in the watchlist">
              <MoversList moves={losers} />
            </Card>
          </div>

          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search watchlist symbol…"
            className="w-full rounded-lg border border-base-border bg-base-surface2 px-3 py-2.5 text-sm text-slate-100 placeholder-slate-600 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 sm:w-72"
          />

          {filtered.length === 0 ? (
            <EmptyBlock title="No symbols match your search" message="Try a different symbol." />
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {filtered.map((tick) => (
                <TickCard key={tick.symbol} tick={tick} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function MoversList({ moves }: { moves: TickOut[] }) {
  if (moves.length === 0) {
    return <p className="text-sm text-slate-500">Not enough data yet.</p>;
  }
  return (
    <ul className="space-y-2">
      {moves.map((t) => (
        <li key={t.symbol} className="flex items-center justify-between text-sm">
          <Link to={`/stocks/${t.symbol}`} className="font-medium text-slate-100 hover:text-brand-300">
            {t.symbol}
          </Link>
          <span className={(t.change_percent ?? 0) >= 0 ? 'text-positive' : 'text-negative'}>
            {formatSignedPct(t.change_percent)}
          </span>
        </li>
      ))}
    </ul>
  );
}

function TickCard({ tick }: { tick: TickOut }) {
  const positive = (tick.change ?? 0) >= 0;
  return (
    <Link to={`/stocks/${tick.symbol}`}>
      <Card className="h-full transition hover:border-brand-500/50 hover:shadow-lg">
        <div className="flex items-start justify-between">
          <p className="text-lg font-bold text-slate-100">{tick.symbol}</p>
          <TickStatusBadge status={tick.status} />
        </div>
        <div className="mt-3 flex items-baseline gap-2">
          <span className="text-2xl font-bold text-slate-100">{formatCurrency(tick.price)}</span>
          {tick.change !== null && (
            <span className={`text-sm font-medium ${positive ? 'text-positive' : 'text-negative'}`}>
              {positive ? '+' : ''}
              {formatCurrency(tick.change)} ({formatSignedPct(tick.change_percent)})
            </span>
          )}
        </div>
        <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
          <span>Vol: {formatVolume(tick.volume)}</span>
          <span>{timeAgo(tick.last_traded_time)}</span>
        </div>
      </Card>
    </Link>
  );
}
