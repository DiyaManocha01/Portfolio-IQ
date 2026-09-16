import React from 'react';
import clsx from 'clsx';
import type { Confidence, DiversificationBenefit, Direction, PortfolioRisk, SentimentLabel, Severity } from '../types/api';

type Tone = 'positive' | 'negative' | 'neutral' | 'warn' | 'brand';

export function Badge({
  children,
  tone = 'neutral',
  className,
}: {
  children: React.ReactNode;
  tone?: Tone;
  className?: string;
}) {
  const toneClasses: Record<Tone, string> = {
    positive: 'bg-positive-bg text-positive border-positive/30',
    negative: 'bg-negative-bg text-negative border-negative/30',
    neutral: 'bg-neutral-bg text-neutral border-neutral/30',
    warn: 'bg-warn-bg text-warn border-warn/30',
    brand: 'bg-brand-500/10 text-brand-300 border-brand-500/30',
  };
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap',
        toneClasses[tone],
        className
      )}
    >
      {children}
    </span>
  );
}

export function DirectionBadge({ direction, label }: { direction: Direction; label?: string }) {
  const map: Record<Direction, { tone: Tone; text: string }> = {
    POSITIVE: { tone: 'positive', text: 'Potentially Positive' },
    NEGATIVE: { tone: 'negative', text: 'Potentially Negative' },
    NEUTRAL: { tone: 'neutral', text: 'Neutral' },
  };
  const cfg = map[direction] ?? map.NEUTRAL;
  return <Badge tone={cfg.tone}>{label ?? cfg.text}</Badge>;
}

export function ConfidenceBadge({ confidence }: { confidence: Confidence }) {
  const tone: Tone = confidence === 'HIGH' ? 'brand' : confidence === 'MEDIUM' ? 'warn' : 'neutral';
  return <Badge tone={tone}>Model Confidence: {confidence}</Badge>;
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  const tone: Tone = severity === 'HIGH' ? 'negative' : severity === 'MEDIUM' ? 'warn' : 'neutral';
  return <Badge tone={tone}>{severity}</Badge>;
}

export function RiskBadge({ risk }: { risk: PortfolioRisk }) {
  const tone: Tone = risk === 'High' ? 'negative' : risk === 'Moderate' ? 'warn' : 'positive';
  return <Badge tone={tone}>{risk} Risk</Badge>;
}

export function SentimentBadge({ label }: { label: SentimentLabel }) {
  const tone: Tone = label === 'POSITIVE' ? 'positive' : label === 'NEGATIVE' ? 'negative' : 'neutral';
  return <Badge tone={tone}>{label.charAt(0) + label.slice(1).toLowerCase()}</Badge>;
}

export function DiversificationBadge({ benefit }: { benefit: DiversificationBenefit }) {
  const tone: Tone = benefit === 'High' ? 'positive' : benefit === 'Moderate' ? 'warn' : 'neutral';
  return <Badge tone={tone}>{benefit} Diversification Benefit</Badge>;
}

export function DataSourceBadge({ source }: { source: 'DEV_SAMPLE' | 'LIVE' }) {
  if (source === 'LIVE') return <Badge tone="brand">Live data</Badge>;
  return (
    <span
      title="This figure is generated from development sample data seeded for demo purposes."
      className="inline-flex items-center gap-1 rounded-full border border-base-border bg-base-surface2 px-2.5 py-0.5 text-[11px] font-medium text-slate-400 cursor-help"
    >
      Development sample data
    </span>
  );
}
