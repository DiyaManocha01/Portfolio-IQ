import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { DrawdownPoint } from '../types/api';
import { formatDate } from '../utils/format';

export function DrawdownChart({ points }: { points: DrawdownPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={points} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="drawdownGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#ef4444" stopOpacity={0} />
            <stop offset="100%" stopColor="#ef4444" stopOpacity={0.35} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#22304d" vertical={false} />
        <XAxis dataKey="date" tickFormatter={(v) => formatDate(v)} stroke="#64748b" tick={{ fontSize: 11 }} minTickGap={40} />
        <YAxis
          stroke="#64748b"
          tick={{ fontSize: 11 }}
          tickFormatter={(v: number) => `${v.toFixed(0)}%`}
          width={50}
          domain={['auto', 0]}
        />
        <Tooltip
          contentStyle={{ background: '#111a2e', border: '1px solid #22304d', borderRadius: 8, fontSize: 12 }}
          labelFormatter={(v) => formatDate(v as string)}
          formatter={(value: number) => [`${value.toFixed(2)}%`, 'Drawdown']}
        />
        <Area type="monotone" dataKey="drawdown_pct" stroke="#ef4444" strokeWidth={1.5} fill="url(#drawdownGradient)" />
      </AreaChart>
    </ResponsiveContainer>
  );
}
