import { Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { AnalysisPoint } from '../types/api';
import { formatDate, formatNumber } from '../utils/format';

export function MacdChart({ points }: { points: AnalysisPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <ComposedChart data={points} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#22304d" vertical={false} />
        <XAxis dataKey="date" tickFormatter={(v) => formatDate(v)} stroke="#64748b" tick={{ fontSize: 11 }} minTickGap={40} />
        <YAxis stroke="#64748b" tick={{ fontSize: 11 }} width={48} tickFormatter={(v) => formatNumber(v, 1)} />
        <ReferenceLine y={0} stroke="#475569" />
        <Tooltip
          contentStyle={{ background: '#111a2e', border: '1px solid #22304d', borderRadius: 8, fontSize: 12 }}
          labelFormatter={(v) => formatDate(v as string)}
          formatter={(value: number, name: string) => [formatNumber(value, 2), name]}
        />
        <Bar dataKey="macd_histogram" name="Histogram" fill="#2b8cff" fillOpacity={0.35} />
        <Line type="monotone" dataKey="macd_line" name="MACD" stroke="#22c55e" strokeWidth={2} dot={false} connectNulls />
        <Line type="monotone" dataKey="macd_signal" name="Signal" stroke="#f59e0b" strokeWidth={2} dot={false} connectNulls />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
