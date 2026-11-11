import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { CandleOut } from '../types/api';
import { formatCurrency, formatDateTime } from '../utils/format';

export function IntradayChart({ candles }: { candles: CandleOut[] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={candles} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#22304d" vertical={false} />
        <XAxis
          dataKey="timestamp"
          tickFormatter={(v) => new Date(v).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}
          stroke="#64748b"
          tick={{ fontSize: 11 }}
          minTickGap={40}
        />
        <YAxis
          stroke="#64748b"
          tick={{ fontSize: 11 }}
          domain={['auto', 'auto']}
          tickFormatter={(v) => formatCurrency(v, { compact: true })}
          width={70}
        />
        <Tooltip
          contentStyle={{ background: '#111a2e', border: '1px solid #22304d', borderRadius: 8, fontSize: 12 }}
          labelFormatter={(v) => formatDateTime(v as string)}
          formatter={(value: number) => [formatCurrency(value), 'Close']}
        />
        <Line type="monotone" dataKey="close" name="Close" stroke="#2b8cff" strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
