import { memo } from 'react';
import { Line, LineChart, ResponsiveContainer, YAxis } from 'recharts';

/** Minimal axes-free line chart for a watchlist card -- real-data upgrade
 * Phase I. Deliberately has no grid/axis/tooltip: it's a glance-level
 * shape indicator, not a readable chart (TickCard links to StockDetailPage
 * for the full IntradayChart). */
export const Sparkline = memo(function Sparkline({ closes, positive }: { closes: number[]; positive: boolean }) {
  if (closes.length < 2) return null;
  const data = closes.map((close, i) => ({ i, close }));
  const stroke = positive ? '#22c55e' : '#f87171';
  return (
    <ResponsiveContainer width="100%" height={32}>
      <LineChart data={data} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
        <YAxis domain={['auto', 'auto']} hide />
        <Line type="monotone" dataKey="close" stroke={stroke} strokeWidth={1.5} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
});
