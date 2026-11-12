import { memo } from 'react';
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { OHLCV } from '../types/api';
import { formatCurrency, formatDate } from '../utils/format';

// Memoized: StockDetailPage re-renders every ~1s on each live-feed tick
// (for its small live-price stat, unrelated to this chart's own data),
// and `points` only ever changes when useAsync actually refetches --
// skipping re-render/re-paint of this otherwise-expensive Recharts tree
// on every tick is a real win, not a premature optimization.
export const PriceHistoryChart = memo(function PriceHistoryChart({ points }: { points: OHLCV[] }) {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={points} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#22304d" vertical={false} />
        <XAxis dataKey="date" tickFormatter={(v) => formatDate(v)} stroke="#64748b" tick={{ fontSize: 11 }} minTickGap={40} />
        <YAxis
          stroke="#64748b"
          tick={{ fontSize: 11 }}
          domain={['auto', 'auto']}
          tickFormatter={(v) => formatCurrency(v, { compact: true })}
          width={70}
        />
        <Tooltip
          contentStyle={{ background: '#111a2e', border: '1px solid #22304d', borderRadius: 8, fontSize: 12 }}
          labelFormatter={(v) => formatDate(v as string)}
          formatter={(value: number, name: string) => [formatCurrency(value), name]}
        />
        <Line type="monotone" dataKey="close" name="Close" stroke="#2b8cff" strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
});
