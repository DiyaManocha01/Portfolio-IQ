import { Card } from './Card';
import { Badge } from './Badge';
import type { MarketRegime, RegimeOut } from '../types/api';

const REGIME_TONE: Record<MarketRegime, 'positive' | 'negative' | 'neutral' | 'warn'> = {
  TRENDING_UP: 'positive',
  TRENDING_DOWN: 'negative',
  SIDEWAYS: 'neutral',
  HIGH_VOLATILITY: 'warn',
  LOW_VOLATILITY: 'neutral',
};

export function RegimeCard({ regime, title }: { regime: RegimeOut; title?: string }) {
  return (
    <Card
      title={title ?? `${regime.symbol} Regime`}
      subtitle="Rule-based classification from trend and volatility statistics -- not a trained model, not a prediction"
    >
      <div className="flex flex-wrap items-center gap-3">
        <Badge tone={REGIME_TONE[regime.regime] ?? 'neutral'}>{regime.display_name}</Badge>
        <span className="text-xs text-slate-500">Confidence: {(regime.confidence * 100).toFixed(0)}%</span>
      </div>
      {regime.note && <p className="mt-2 text-xs text-slate-500">{regime.note}</p>}
      {regime.factors.length > 0 && (
        <ul className="mt-3 space-y-1.5 text-xs text-slate-400">
          {regime.factors.map((f) => (
            <li key={f.name}>
              <span className="font-medium text-slate-300">{f.name}:</span> {f.explanation}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
