import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { BenchmarkPoint, PerformancePoint } from '../types/api';
import { formatCurrency, formatDate } from '../utils/format';

export function BenchmarkComparisonChart({
  points,
  benchmark,
}: {
  points: PerformancePoint[];
  benchmark: BenchmarkPoint[];
}) {
  const byDate = new Map<string, { date: string; portfolio?: number; benchmark?: number }>();
  for (const p of points) {
    byDate.set(p.date, { ...(byDate.get(p.date) ?? { date: p.date }), portfolio: p.value });
  }
  for (const p of benchmark) {
    byDate.set(p.date, { ...(byDate.get(p.date) ?? { date: p.date }), benchmark: p.value });
  }
  const merged = Array.from(byDate.values()).sort((a, b) => a.date.localeCompare(b.date));

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={merged} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#22304d" vertical={false} />
        <XAxis dataKey="date" tickFormatter={(v) => formatDate(v)} stroke="#64748b" tick={{ fontSize: 11 }} minTickGap={40} />
        <YAxis
          stroke="#64748b"
          tick={{ fontSize: 11 }}
          tickFormatter={(v) => formatCurrency(v, { compact: true })}
          width={70}
        />
        <Tooltip
          contentStyle={{ background: '#111a2e', border: '1px solid #22304d', borderRadius: 8, fontSize: 12 }}
          labelFormatter={(v) => formatDate(v as string)}
          formatter={(value: number, name: string) => [formatCurrency(value), name === 'portfolio' ? 'Portfolio' : 'NIFTY 50 Benchmark']}
        />
        <Legend formatter={(v) => (v === 'portfolio' ? 'Portfolio' : 'NIFTY 50 Benchmark')} />
        <Line type="monotone" dataKey="portfolio" stroke="#2b8cff" strokeWidth={2} dot={false} connectNulls />
        <Line type="monotone" dataKey="benchmark" stroke="#64748b" strokeDasharray="4 3" strokeWidth={1.5} dot={false} connectNulls />
      </LineChart>
    </ResponsiveContainer>
  );
}
