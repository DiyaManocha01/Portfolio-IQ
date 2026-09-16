import { Link, useParams } from 'react-router-dom';
import { useAsync } from '../hooks/useAsync';
import * as discoverService from '../services/discover';
import { Card } from '../components/Card';
import { ErrorBlock, LoadingBlock } from '../components/States';
import { HorizontalBarChart } from '../charts/HorizontalBarChart';
import { colorForIndex } from '../charts/palette';

export default function PortfolioFitPage() {
  const { symbol = '' } = useParams();
  const fit = useAsync(() => discoverService.getPortfolioFit(symbol), [symbol]);

  return (
    <div className="space-y-6">
      <Link to="/discover" className="text-xs font-medium text-brand-400 hover:text-brand-300">
        &larr; Back to Discover
      </Link>

      {fit.loading && <LoadingBlock />}
      {fit.error && <ErrorBlock message={fit.error} onRetry={fit.reload} />}

      {fit.data && (
        <>
          <div className="rounded-2xl border border-brand-500/30 bg-gradient-to-br from-brand-500/10 to-transparent p-6 sm:p-8">
            <p className="text-xs font-semibold uppercase tracking-wide text-brand-300">Portfolio Fit</p>
            <div className="mt-2 flex flex-wrap items-end gap-4">
              <h1 className="text-3xl font-bold text-slate-100 sm:text-4xl">
                {fit.data.symbol} <span className="text-base font-normal text-slate-400">— {fit.data.name}</span>
              </h1>
            </div>
            <div className="mt-5 flex items-center gap-4">
              <div className="text-6xl font-extrabold text-brand-400">{fit.data.fit_score.toFixed(1)}</div>
              <div className="text-sm text-slate-400 max-w-xs">
                Estimated fit score (0-100) combining model outlook, risk, correlation, sector balance, and your
                current portfolio composition.
              </div>
            </div>
          </div>

          <Card title="Fit Factor Breakdown" subtitle="Contribution of each factor to the overall fit score, sorted by impact">
            <HorizontalBarChart
              data={fit.data.factors.map((f, i) => ({ label: f.name, value: f.contribution, color: colorForIndex(i) }))}
              height={Math.max(220, fit.data.factors.length * 46)}
              valueFormatter={(v) => v.toFixed(1)}
            />
            <div className="mt-4 space-y-2">
              {fit.data.factors.map((f) => (
                <div key={f.name} className="flex items-start justify-between gap-3 rounded-lg border border-base-border bg-base-surface2 px-3 py-2">
                  <div>
                    <p className="text-sm font-semibold text-slate-100">{f.name}</p>
                    <p className="text-xs text-slate-400">{f.explanation}</p>
                  </div>
                  <div className="shrink-0 text-sm font-bold text-brand-400">+{f.contribution.toFixed(1)}</div>
                </div>
              ))}
            </div>
          </Card>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Card title="Why it may fit" className="border-positive/30">
              {fit.data.strengths.length > 0 ? (
                <ul className="space-y-2">
                  {fit.data.strengths.map((s, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-slate-200">
                      <span className="mt-0.5 text-positive">&#10003;</span>
                      <span>{s}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-slate-500">No specific strengths identified.</p>
              )}
            </Card>

            <Card title="Potential concerns" className="border-warn/30">
              {fit.data.concerns.length > 0 ? (
                <ul className="space-y-2">
                  {fit.data.concerns.map((c, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-slate-200">
                      <span className="mt-0.5 text-warn">&#9888;</span>
                      <span>{c}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-slate-500">No specific concerns identified.</p>
              )}
            </Card>
          </div>

          <Card title="Weighting Methodology" subtitle="How much each factor contributes to the fit score by design">
            <div className="flex flex-wrap gap-3">
              {Object.entries(fit.data.weights_used).map(([key, weight]) => (
                <div key={key} className="rounded-lg border border-base-border bg-base-surface2 px-3 py-2 text-xs">
                  <span className="capitalize text-slate-400">{key.replace(/_/g, ' ')}: </span>
                  <span className="font-semibold text-slate-200">{(weight * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
