import React from 'react';
import { DisclaimerFooter } from '../components/DisclaimerFooter';

export function AuthShell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col bg-base-bg">
      <div className="flex flex-1 items-center justify-center px-4 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex flex-col items-center text-center">
            <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-brand-600 text-lg font-bold text-white">
              P
            </div>
            <h1 className="text-xl font-bold text-slate-100">{title}</h1>
            <p className="mt-1 text-sm text-slate-400">{subtitle}</p>
          </div>
          <div className="rounded-2xl border border-base-border bg-base-surface p-6 shadow-card">{children}</div>
        </div>
      </div>
      <DisclaimerFooter />
    </div>
  );
}
