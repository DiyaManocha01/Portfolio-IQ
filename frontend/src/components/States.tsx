import React from 'react';

export function Skeleton({ className = 'h-4 w-full' }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-base-surface2 ${className}`} />;
}

export function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <div className="rounded-xl border border-base-border bg-base-surface p-5 space-y-3">
      <Skeleton className="h-4 w-1/3" />
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className="h-3 w-full" />
      ))}
    </div>
  );
}

export function LoadingBlock({ label = 'Loading data…' }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-slate-400">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-brand-500 border-t-transparent" />
      <p className="text-sm">{label}</p>
    </div>
  );
}

export function ErrorBlock({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-negative/30 bg-negative-bg py-12 px-6 text-center">
      <svg xmlns="http://www.w3.org/2000/svg" className="h-8 w-8 text-negative" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
        <circle cx="12" cy="12" r="9" />
        <path d="M12 8v5" strokeLinecap="round" />
        <path d="M12 16h.01" strokeLinecap="round" />
      </svg>
      <p className="text-sm text-slate-200 max-w-sm">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="rounded-lg border border-negative/40 px-3 py-1.5 text-xs font-medium text-negative hover:bg-negative/10 transition"
        >
          Try again
        </button>
      )}
    </div>
  );
}

export function EmptyBlock({
  title,
  message,
  tone = 'neutral',
  icon,
}: {
  title: string;
  message: string;
  tone?: 'neutral' | 'positive';
  icon?: React.ReactNode;
}) {
  const toneClasses = tone === 'positive' ? 'border-positive/30 bg-positive-bg' : 'border-base-border bg-base-surface2';
  const textClass = tone === 'positive' ? 'text-positive' : 'text-slate-300';
  return (
    <div className={`flex flex-col items-center justify-center gap-2 rounded-xl border ${toneClasses} py-10 px-6 text-center`}>
      {icon ?? (
        <svg xmlns="http://www.w3.org/2000/svg" className={`h-7 w-7 ${textClass}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M9 12.75l1.5 1.5 3-3.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
      <p className={`text-sm font-semibold ${textClass}`}>{title}</p>
      <p className="text-xs text-slate-400 max-w-sm">{message}</p>
    </div>
  );
}
