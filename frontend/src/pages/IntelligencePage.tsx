import { useAsync } from '../hooks/useAsync';
import * as portfolioService from '../services/portfolio';
import { Card } from '../components/Card';
import { StatCard } from '../components/StatCard';
import { ErrorBlock, LoadingBlock, EmptyBlock } from '../components/States';
import { SeverityBadge, DataSourceBadge } from '../components/Badge';
import { HorizontalBarChart } from '../charts/HorizontalBarChart';
import { CorrelationHeatmap } from '../charts/CorrelationHeatmap';
import { AllocationDonut } from '../charts/AllocationDonut';
import { BenchmarkComparisonChart } from '../charts/BenchmarkComparisonChart';
import { DrawdownChart } from '../charts/DrawdownChart';
import { colorForIndex } from '../charts/palette';
import { WeaknessCard } from '../components/WeaknessCard';
import { formatCurrency, formatNumber, formatPct, formatProbabilityPct, formatSignedPct } from '../utils/format';
import type { HeatmapItem } from '../types/api';

export default function IntelligencePage() {
  const risk = useAsync(() => portfolioService.getRisk(), []);
  const attribution = useAsync(() => portfolioService.getRiskAttribution(), []);
  const advanced = useAsync(() => portfolioService.getAdvancedPerformance(), []);
  const heatmap = useAsync(() => portfolioService.getHeatmap(), []);
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

      {/* Risk attribution section */}
      <section className="space-y-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Risk Attribution</h2>
        {attribution.loading && <LoadingBlock />}
        {attribution.error && <ErrorBlock message={attribution.error} onRetry={attribution.reload} />}
        {attribution.data && attribution.data.attributions.length > 0 && (
          <Card
            title="% of Money vs. % of Risk"
            subtitle="A holding whose risk share is well above its money share is contributing more risk than its position size alone would suggest"
          >
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-sm">
                <thead>
                  <tr className="border-b border-base-border text-left text-xs uppercase tracking-wide text-slate-500">
                    <th className="pb-2 pr-3 font-medium">Symbol</th>
                    <th className="pb-2 pr-3 font-medium text-right">Weight %</th>
                    <th className="pb-2 pr-3 font-medium text-right">Risk %</th>
                    <th className="pb-2 pr-3 font-medium text-right">Concentration Ratio</th>
                  </tr>
                </thead>
                <tbody>
                  {attribution.data.attributions.map((a) => {
                    const ratioTone =
                      a.risk_concentration_ratio >= 1.3
                        ? 'text-negative'
                        : a.risk_concentration_ratio <= 0.8
                          ? 'text-positive'
                          : 'text-slate-200';
                    return (
                      <tr key={a.symbol} className="border-b border-base-border/60 last:border-0">
                        <td className="py-2.5 pr-3">
                          <div className="font-semibold text-slate-100">{a.symbol}</div>
                          <div className="text-xs text-slate-500">{a.sector}</div>
                        </td>
                        <td className="py-2.5 pr-3 text-right text-slate-300">{formatPct(a.weight_pct)}</td>
                        <td className="py-2.5 pr-3 text-right text-slate-300">{formatPct(a.risk_contribution_pct)}</td>
                        <td className={`py-2.5 pr-3 text-right font-semibold ${ratioTone}`}>
                          {formatNumber(a.risk_concentration_ratio, 2)}x
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-[11px] text-slate-500">
              Ratio &gt; 1 means a holding contributes disproportionately more risk than its money weight;
              &lt; 1 means less. Portfolio annualized volatility:{' '}
              {formatProbabilityPct(attribution.data.portfolio_annualized_volatility)}.
            </p>
          </Card>
        )}
      </section>

      {/* Advanced Performance section */}
      <section className="space-y-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Advanced Performance</h2>
        {advanced.loading && <LoadingBlock />}
        {advanced.error && <ErrorBlock message={advanced.error} onRetry={advanced.reload} />}
        {advanced.data && (
          <>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <StatCard
                label="Unrealized P&L"
                value={formatCurrency(advanced.data.unrealized_pnl)}
                tone={advanced.data.unrealized_pnl >= 0 ? 'positive' : 'negative'}
              />
              <StatCard
                label="Realized P&L"
                value={formatCurrency(advanced.data.realized_pnl)}
                tone={advanced.data.realized_pnl >= 0 ? 'positive' : 'negative'}
                sub="Since Phase 31's transaction logging began -- sells before then aren't included"
              />
              <StatCard
                label="Total P&L"
                value={formatCurrency(advanced.data.total_pnl)}
                tone={advanced.data.total_pnl >= 0 ? 'positive' : 'negative'}
                sub={<DataSourceBadge source={advanced.data.data_source} />}
              />
            </div>

            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
              <StatCard
                label="CAGR"
                value={advanced.data.cagr !== null ? formatSignedPct(advanced.data.cagr * 100) : '—'}
                tone={advanced.data.cagr !== null && advanced.data.cagr >= 0 ? 'positive' : 'negative'}
              />
              <StatCard
                label="NIFTY 50 CAGR"
                value={advanced.data.benchmark_cagr !== null ? formatSignedPct(advanced.data.benchmark_cagr * 100) : '—'}
              />
              <StatCard label="Beta" value={advanced.data.beta !== null ? advanced.data.beta.toFixed(2) : '—'} />
              <StatCard
                label="Alpha (ann.)"
                value={advanced.data.alpha !== null ? formatSignedPct(advanced.data.alpha * 100) : '—'}
                tone={advanced.data.alpha !== null && advanced.data.alpha >= 0 ? 'positive' : 'negative'}
              />
              <StatCard
                label="Tracking Error"
                value={advanced.data.tracking_error !== null ? formatPct(advanced.data.tracking_error * 100) : '—'}
              />
              <StatCard
                label="Information Ratio"
                value={advanced.data.information_ratio !== null ? advanced.data.information_ratio.toFixed(2) : '—'}
              />
            </div>
            <p className="text-xs text-slate-600">
              Risk-free rate assumed: {(advanced.data.risk_free_rate_assumed * 100).toFixed(0)}%. Beta/alpha/tracking
              error/information ratio require at least 20 overlapping trading days against NIFTY 50 -- shown as "—"
              otherwise, not a misleading number from too little data.
            </p>

            <Card title="Portfolio vs. NIFTY 50" subtitle="Portfolio value compared to a NIFTY 50 buy-and-hold with the same starting value">
              {advanced.data.points.length > 0 ? (
                <BenchmarkComparisonChart points={advanced.data.points} benchmark={advanced.data.benchmark} />
              ) : (
                <EmptyBlock title="Not enough data" message="Add holdings with price history to compare performance." />
              )}
            </Card>

            <Card title="Drawdown" subtitle="Decline from the running peak portfolio value over the lookback window">
              {advanced.data.drawdown.length > 0 ? (
                <DrawdownChart points={advanced.data.drawdown} />
              ) : (
                <EmptyBlock title="Not enough data" message="Add holdings with price history to compute drawdown." />
              )}
            </Card>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              <Card title="Holding Contribution to P&L" subtitle="Share of total unrealized P&L contributed by each holding">
                {advanced.data.holding_contributions.length > 0 ? (
                  <HorizontalBarChart
                    data={advanced.data.holding_contributions.map((c, i) => ({
                      label: c.symbol,
                      value: c.contribution_pct,
                      color: colorForIndex(i),
                    }))}
                    valueFormatter={(v) => `${v.toFixed(1)}%`}
                    height={Math.max(200, advanced.data.holding_contributions.length * 38)}
                  />
                ) : (
                  <EmptyBlock title="No contribution data" message="Add holdings to compute P&L contribution." />
                )}
              </Card>

              <Card title="Sector Contribution to P&L" subtitle="Share of total unrealized P&L contributed by each sector">
                {advanced.data.sector_contributions.length > 0 ? (
                  <HorizontalBarChart
                    data={advanced.data.sector_contributions.map((c, i) => ({
                      label: c.sector,
                      value: c.contribution_pct,
                      color: colorForIndex(i),
                    }))}
                    valueFormatter={(v) => `${v.toFixed(1)}%`}
                    height={Math.max(200, advanced.data.sector_contributions.length * 38)}
                  />
                ) : (
                  <EmptyBlock title="No contribution data" message="Add holdings to compute sector contribution." />
                )}
              </Card>
            </div>
          </>
        )}
      </section>

      {/* Live Portfolio Heatmap section (real-data upgrade Phase E) */}
      <section className="space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Live Portfolio Heatmap</h2>
        {heatmap.loading && <LoadingBlock />}
        {heatmap.error && <ErrorBlock message={heatmap.error} onRetry={heatmap.reload} />}
        {heatmap.data && heatmap.data.items.length > 0 && (
          <Card
            title="Today's Move by Holding"
            subtitle="Each tile's own daily price % change, sized by portfolio weight"
            action={<DataSourceBadge source={heatmap.data.data_source} />}
          >
            <PortfolioHeatmapGrid items={heatmap.data.items} />
          </Card>
        )}
        {heatmap.data && heatmap.data.items.length === 0 && (
          <EmptyBlock title="No holdings yet" message="Add stocks to your portfolio to see the daily heatmap." />
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

function PortfolioHeatmapGrid({ items }: { items: HeatmapItem[] }) {
  const sorted = [...items].sort((a, b) => b.weight_pct - a.weight_pct);
  const maxAbsMove = Math.max(1, ...sorted.map((i) => Math.abs(i.day_pnl_pct)));

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
      {sorted.map((item) => {
        const positive = item.day_pnl_pct >= 0;
        // Opacity scales with how large today's move is relative to the
        // biggest mover in this portfolio -- a visual intensity cue, not a
        // claim about statistical significance.
        const intensity = Math.min(1, Math.abs(item.day_pnl_pct) / maxAbsMove);
        const bg = positive ? `rgba(34,197,94,${0.12 + intensity * 0.35})` : `rgba(239,68,68,${0.12 + intensity * 0.35})`;
        return (
          <div
            key={item.symbol}
            className="rounded-lg border border-base-border p-3"
            style={{ backgroundColor: bg }}
            title={`${item.sector} -- ${item.weight_pct.toFixed(1)}% of portfolio -- contributes ${item.contribution_to_daily_pnl_pct.toFixed(1)}% of today's total P&L`}
          >
            <p className="text-sm font-bold text-slate-100">{item.symbol}</p>
            <p className={`mt-1 text-lg font-bold ${positive ? 'text-positive' : 'text-negative'}`}>
              {formatSignedPct(item.day_pnl_pct)}
            </p>
            <p className="mt-1 text-[11px] text-slate-400">
              {item.weight_pct.toFixed(1)}% weight &middot; {formatCurrency(item.day_pnl, { compact: true })}
            </p>
          </div>
        );
      })}
    </div>
  );
}
