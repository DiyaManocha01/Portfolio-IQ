import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { PerformancePoint } from '../types/api';
import { formatCurrency, formatDate } from '../utils/format';

export function PerformanceChart({ points }: { points: PerformancePoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={points} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="valueGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2b8cff" stopOpacity={0.35} />
            <stop offset="100%" stopColor="#2b8cff" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#22304d" vertical={false} />
        <XAxis
          dataKey="date"
          tickFormatter={(v) => formatDate(v)}
          stroke="#64748b"
          tick={{ fontSize: 11 }}
          minTickGap={40}
        />
        <YAxis
          stroke="#64748b"
          tick={{ fontSize: 11 }}
          tickFormatter={(v) => formatCurrency(v, { compact: true })}
          width={70}
        />
        <Tooltip
          contentStyle={{ background: '#111a2e', border: '1px solid #22304d', borderRadius: 8, fontSize: 12 }}
          labelFormatter={(v) => formatDate(v as string)}
          formatter={(value: number, name: string) => [formatCurrency(value), name === 'value' ? 'Portfolio Value' : 'Invested']}
        />
        <Area type="monotone" dataKey="invested" stroke="#64748b" strokeDasharray="4 3" fill="none" strokeWidth={1.5} />
        <Area type="monotone" dataKey="value" stroke="#2b8cff" strokeWidth={2} fill="url(#valueGradient)" />
      </AreaChart>
    </ResponsiveContainer>
  );
}
