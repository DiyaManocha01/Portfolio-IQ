import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import type { AllocationSlice } from '../types/api';
import { colorForIndex } from './palette';
import { formatCurrency } from '../utils/format';

export function AllocationDonut({ data }: { data: AllocationSlice[] }) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <PieChart>
        <Pie
          data={data}
          dataKey="value"
          nameKey="label"
          cx="50%"
          cy="45%"
          innerRadius={60}
          outerRadius={95}
          paddingAngle={2}
        >
          {data.map((entry, i) => (
            <Cell key={entry.label} fill={colorForIndex(i)} stroke="#0b1120" strokeWidth={2} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{ background: '#111a2e', border: '1px solid #22304d', borderRadius: 8, fontSize: 12 }}
          formatter={(value: number, name: string, item) => [
            `${formatCurrency(value)} (${(item.payload as AllocationSlice).pct.toFixed(1)}%)`,
            name,
          ]}
        />
        <Legend
          verticalAlign="bottom"
          height={56}
          wrapperStyle={{ fontSize: 11, color: '#94a3b8' }}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
