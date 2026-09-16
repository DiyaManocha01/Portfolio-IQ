import React from 'react';
import clsx from 'clsx';

export function StatCard({
  label,
  value,
  sub,
  tone = 'default',
  icon,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: 'default' | 'positive' | 'negative';
  icon?: React.ReactNode;
}) {
  const valueTone = tone === 'positive' ? 'text-positive' : tone === 'negative' ? 'text-negative' : 'text-slate-100';
  return (
    <div className="rounded-xl border border-base-border bg-base-surface p-4 shadow-card">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</p>
        {icon && <div className="text-slate-500">{icon}</div>}
      </div>
      <p className={clsx('mt-2 text-xl font-bold sm:text-2xl', valueTone)}>{value}</p>
      {sub && <div className="mt-1 text-xs text-slate-400">{sub}</div>}
    </div>
  );
}
