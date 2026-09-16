import type { Prediction } from '../types/api';
import { ConfidenceBadge, DirectionBadge } from './Badge';
import { formatProbabilityPct } from '../utils/format';

export function PredictionCard({ prediction, symbol }: { prediction: Prediction; symbol: string }) {
  return (
    <div className="rounded-lg border border-base-border bg-base-surface2 p-4">
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold text-slate-100">{symbol}</span>
        <DirectionBadge direction={prediction.direction} />
      </div>
      <div className="mt-3 flex items-center gap-4">
        <div>
          <p className="text-[11px] uppercase tracking-wide text-slate-500">Model Probability</p>
          <p className="text-lg font-bold text-slate-100">{formatProbabilityPct(prediction.probability)}</p>
        </div>
        <div className="h-8 w-px bg-base-border" />
        <div>
          <ConfidenceBadge confidence={prediction.confidence} />
        </div>
      </div>
      {prediction.important_features?.length > 0 && (
        <div className="mt-3">
          <p className="text-[11px] uppercase tracking-wide text-slate-500 mb-1">Key Signals</p>
          <ul className="space-y-0.5 text-xs text-slate-400 list-disc list-inside">
            {prediction.important_features.slice(0, 3).map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="mt-3 text-[11px] leading-relaxed text-slate-500 italic">{prediction.disclaimer}</p>
    </div>
  );
}
