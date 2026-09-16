import { useAsync } from '../hooks/useAsync';
import * as portfolioService from '../services/portfolio';
import { Card } from '../components/Card';
import { StatCard } from '../components/StatCard';
import { ErrorBlock, LoadingBlock, EmptyBlock } from '../components/States';
import { SeverityBadge, DataSourceBadge } from '../components/Badge';
import { HorizontalBarChart } from '../charts/HorizontalBarChart';
import { CorrelationHeatmap } from '../charts/CorrelationHeatmap';
import { AllocationDonut } from '../charts/AllocationDonut';
import { colorForIndex } from '../charts/palette';
import { WeaknessCard } from '../components/WeaknessCard';
import { formatNumber, formatProbabilityPct, formatSignedPct } from '../utils/format';

export default function IntelligencePage() {
  const risk = useAsync(() => portfolioService.getRisk(), []);
  const health = useAsync(() => portfolioService.getHealth(), []);
  const weaknesses = useAsync(() => portfolioService.getWeaknesses(), []);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Portfolio Intelligence</h1>
        <p className="mt-1 text-sm text-slate-400">Deep-dive into risk, health, and detected weaknesses across your portfolio.</p>
      </div>

      {/* Risk section */}
      <section className="space-y-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Risk Analysis</h2>
        {risk.loading && <LoadingBlock />}
        {risk.error && <ErrorBlock message={risk.error} onRetry={risk.reload} />}
        {risk.data && (
          <>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard label="Annualized Volatility" value={formatProbabilityPct(risk.data.annualized_volatility)} />
              <StatCard label="Sharpe Ratio" value={formatNumber(risk.data.sharpe_ratio, 2)} />
              <StatCard
                label="Max Drawdown"
                value={formatSignedPct(risk.data.max_drawdown * 100)}
                tone={risk.data.max_drawdown < 0 ? 'negative' : 'default'}
              />
              <StatCard
                label="Top Stock Concentration"
                value={formatProbabilityPct(risk.data.top_stock_concentration_pct / 100)}
                sub={<DataSourceBadge source={risk.data.data_source} />}
              />
            </div>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              <Card title="Risk Contribution by Holding" subtitle="Share of total portfolio risk contributed by each stock">
                {risk.data.risk_contributions.length > 0 ? (
                  <HorizontalBarChart
                    data={risk.data.risk_contributions.map((r, i) => ({
                      label: r.symbol,
                      value: r.risk_contribution_pct,
                      color: colorForIndex(i),
                    }))}
                    valueFormatter={(v) => `${v.toFixed(1)}%`}
                    height={Math.max(200, risk.data.risk_contributions.length * 38)}
                  />
                ) : (
                  <EmptyBlock title="No risk contribution data" message="Add holdings to compute risk contributions." />
                )}
              </Card>

              <Card title="Sector Concentration" subtitle="Portfolio value by sector">
                {risk.data.sector_concentration.length > 0 ? (
                  <AllocationDonut data={risk.data.sector_concentration} />
                ) : (
                  <EmptyBlock title="No sector data" message="Add holdings to compute sector concentration." />
                )}
              </Card>
            </div>

            <Card title="Correlation Matrix" subtitle="Historical price correlation between held stocks">
              {risk.data.correlation_matrix.length > 0 ? (
                <CorrelationHeatmap matrix={risk.data.correlation_matrix} />
              ) : (
                <EmptyBlock title="Not enough data" message="Correlation requires at least two holdings with price history." />
              )}
            </Card>
          </>
        )}
      </section>

      {/* Health section */}
      <section className="space-y-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Portfolio Health</h2>
        {health.loading && <LoadingBlock />}
        {health.error && <ErrorBlock message={health.error} onRetry={health.reload} />}
        {health.data && (
          <Card
            title={`Overall Health Score: ${health.data.overall_health.toFixed(0)} / 100`}
            subtitle="Component scores, each on a 0-100 scale"
          >
            <HorizontalBarChart
              data={health.data.components.map((c, i) => ({ label: c.name, value: c.score, color: colorForIndex(i) }))}
              valueFormatter={(v) => v.toFixed(0)}
              domain={[0, 100]}
              height={Math.max(200, health.data.components.length * 42)}
            />
            <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
              {health.data.components.map((c) => (
                <div key={c.name} className="rounded-lg border border-base-border bg-base-surface2 p-3">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-semibold text-slate-100">{c.name}</p>
                    <p className="text-sm font-bold text-brand-400">{c.score.toFixed(0)}</p>
                  </div>
                  <p className="mt-1 text-xs text-slate-400">{c.description}</p>
                </div>
              ))}
            </div>
          </Card>
        )}
      </section>

      {/* Weaknesses section */}
      <section className="space-y-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Detected Weaknesses</h2>
        {weaknesses.loading && <LoadingBlock />}
        {weaknesses.error && <ErrorBlock message={weaknesses.error} onRetry={weaknesses.reload} />}
        {weaknesses.data && weaknesses.data.weaknesses.length === 0 && (
          <EmptyBlock
            tone="positive"
            title="No major weaknesses detected"
            message="Your portfolio currently shows no significant concentration, correlation, or risk concerns."
          />
        )}
        {weaknesses.data && weaknesses.data.weaknesses.length > 0 && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {weaknesses.data.weaknesses.map((w, i) => (
              <WeaknessCard key={i} weakness={w} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
