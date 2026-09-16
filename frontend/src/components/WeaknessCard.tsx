import type { Weakness } from '../types/api';
import { SeverityBadge } from './Badge';

export function WeaknessCard({ weakness }: { weakness: Weakness }) {
  return (
    <div className="rounded-lg border border-base-border bg-base-surface2 p-4">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-semibold text-slate-100">{weakness.title}</p>
        <SeverityBadge severity={weakness.severity} />
      </div>
      <p className="mt-2 text-xs leading-relaxed text-slate-400">{weakness.explanation}</p>
      <p className="mt-2 text-[11px] font-medium text-slate-500">{weakness.supporting_metric}</p>
    </div>
  );
}
