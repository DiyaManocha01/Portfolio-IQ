import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { AnalysisPoint } from '../types/api';
import { formatDate, formatNumber } from '../utils/format';

export function RsiChart({ points }: { points: AnalysisPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={points} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#22304d" vertical={false} />
        <XAxis dataKey="date" tickFormatter={(v) => formatDate(v)} stroke="#64748b" tick={{ fontSize: 11 }} minTickGap={40} />
        <YAxis domain={[0, 100]} stroke="#64748b" tick={{ fontSize: 11 }} width={36} />
        <ReferenceLine y={70} stroke="#f87171" strokeDasharray="4 4" strokeOpacity={0.6} />
        <ReferenceLine y={30} stroke="#22c55e" strokeDasharray="4 4" strokeOpacity={0.6} />
        <Tooltip
          contentStyle={{ background: '#111a2e', border: '1px solid #22304d', borderRadius: 8, fontSize: 12 }}
          labelFormatter={(v) => formatDate(v as string)}
          formatter={(value: number) => [formatNumber(value, 1), 'RSI (14)']}
        />
        <Line type="monotone" dataKey="rsi_14" name="RSI (14)" stroke="#a78bfa" strokeWidth={2} dot={false} connectNulls />
      </LineChart>
    </ResponsiveContainer>
  );
}
