import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

export interface BarDatum {
  label: string;
  value: number;
  color?: string;
}

export function HorizontalBarChart({
  data,
  height = 260,
  valueFormatter,
  domain,
  defaultColor = '#2b8cff',
}: {
  data: BarDatum[];
  height?: number;
  valueFormatter?: (v: number) => string;
  domain?: [number, number];
  defaultColor?: string;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, left: 8, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#22304d" horizontal={false} />
        <XAxis type="number" stroke="#64748b" tick={{ fontSize: 11 }} domain={domain} tickFormatter={valueFormatter} />
        <YAxis
          type="category"
          dataKey="label"
          stroke="#64748b"
          tick={{ fontSize: 11 }}
          width={140}
        />
        <Tooltip
          contentStyle={{ background: '#111a2e', border: '1px solid #22304d', borderRadius: 8, fontSize: 12 }}
          formatter={(value: number) => [valueFormatter ? valueFormatter(value) : value, 'Value']}
        />
        <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={16}>
          {data.map((entry, i) => (
            <Cell key={i} fill={entry.color ?? defaultColor} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
