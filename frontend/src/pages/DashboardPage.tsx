import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAsync } from '../hooks/useAsync';
import * as portfolioService from '../services/portfolio';
import * as stockService from '../services/stocks';
import type { Holding, NewsItem, Prediction, Weakness } from '../types/api';
import { Card } from '../components/Card';
import { StatCard } from '../components/StatCard';
import { HoldingsTable } from '../components/HoldingsTable';
import { PredictionCard } from '../components/PredictionCard';
import { NewsRow } from '../components/NewsCard';
import { WeaknessCard } from '../components/WeaknessCard';
import { RiskBadge, SeverityBadge } from '../components/Badge';
import { ErrorBlock, LoadingBlock, EmptyBlock, SkeletonCard } from '../components/States';
import { PerformanceChart } from '../charts/PerformanceChart';
import { AllocationDonut } from '../charts/AllocationDonut';
import { formatCurrency, formatSignedPct } from '../utils/format';
import { getErrorMessage } from '../services/api';

export default function DashboardPage() {
  const summary = useAsync(() => portfolioService.getSummary(), []);
  const performance = useAsync(() => portfolioService.getPerformance(180), []);
  const allocation = useAsync(() => portfolioService.getAllocation(), []);
  const holdings = useAsync(() => portfolioService.getHoldings(), []);
  const health = useAsync(() => portfolioService.getHealth(), []);
  const weaknesses = useAsync(() => portfolioService.getWeaknesses(), []);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Dashboard</h1>
        <p className="mt-1 text-sm text-slate-400">A real-time snapshot of your portfolio's value, risk, and AI-driven insights.</p>
      </div>

      <SummaryRow summary={summary.data} loading={summary.loading} error={summary.error} onRetry={summary.reload} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card title="Portfolio Performance" subtitle="Value vs. invested amount over the last 180 days">
          {performance.loading && <LoadingBlock />}
          {performance.error && <ErrorBlock message={performance.error} onRetry={performance.reload} />}
          {performance.data && performance.data.points.length > 0 && <PerformanceChart points={performance.data.points} />}
          {performance.data && performance.data.points.length === 0 && (
            <EmptyBlock title="No performance history yet" message="Add holdings to start tracking portfolio value over time." />
          )}
        </Card>

        <Card title="Portfolio Allocation" subtitle="Current value distribution by stock">
          {allocation.loading && <LoadingBlock />}
          {allocation.error && <ErrorBlock message={allocation.error} onRetry={allocation.reload} />}
          {allocation.data && allocation.data.by_stock.length > 0 && <AllocationDonut data={allocation.data.by_stock} />}
          {allocation.data && allocation.data.by_stock.length === 0 && (
            <EmptyBlock title="No holdings yet" message="Add stocks to your portfolio to see allocation." />
          )}
        </Card>
      </div>

      <Card title="Sector Allocation" subtitle="Current value distribution by sector">
        {allocation.loading && <LoadingBlock />}
        {allocation.error && <ErrorBlock message={allocation.error} onRetry={allocation.reload} />}
        {allocation.data && allocation.data.by_sector.length > 0 && <AllocationDonut data={allocation.data.by_sector} />}
        {allocation.data && allocation.data.by_sector.length === 0 && (
          <EmptyBlock title="No sector data yet" message="Add stocks to your portfolio to see sector exposure." />
        )}
      </Card>

      <Card
        title="Top Holdings"
        subtitle="All positions in your current portfolio"
        action={
          <Link to="/portfolio" className="text-xs font-medium text-brand-400 hover:text-brand-300">
            Manage holdings &rarr;
          </Link>
        }
      >
        {holdings.loading && <LoadingBlock />}
        {holdings.error && <ErrorBlock message={holdings.error} onRetry={holdings.reload} />}
        {holdings.data && holdings.data.length > 0 && <HoldingsTable holdings={holdings.data} />}
        {holdings.data && holdings.data.length === 0 && (
          <EmptyBlock title="No holdings yet" message="Head to My Portfolio to add your first stock." />
        )}
      </Card>

      <AiMarketOutlookSection holdings={holdings.data} />

      <Card title="Portfolio Intelligence Summary" subtitle="Diversification, concentration, and key risk observations">
        <IntelligenceSummary
          healthData={health.data}
          healthLoading={health.loading}
          healthError={health.error}
          onHealthRetry={health.reload}
          weaknessesData={weaknesses.data?.weaknesses ?? null}
          weaknessesLoading={weaknesses.loading}
          weaknessesError={weaknesses.error}
          onWeaknessesRetry={weaknesses.reload}
        />
      </Card>

      <RecentNewsSection holdings={holdings.data} />
    </div>
  );
}

function SummaryRow({
  summary,
  loading,
  error,
  onRetry,
}: {
  summary: import('../types/api').PortfolioSummary | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <SkeletonCard key={i} lines={1} />
        ))}
      </div>
    );
  }
  if (error) return <ErrorBlock message={error} onRetry={onRetry} />;
  if (!summary) return null;

  const pnlPositive = summary.total_pnl >= 0;

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
      <StatCard label="Portfolio Value" value={formatCurrency(summary.portfolio_value, { compact: true })} />
      <StatCard label="Invested Amount" value={formatCurrency(summary.invested_amount, { compact: true })} />
      <StatCard
        label="Total P&L"
        value={`${pnlPositive ? '+' : ''}${formatCurrency(summary.total_pnl, { compact: true })}`}
        tone={pnlPositive ? 'positive' : 'negative'}
      />
      <StatCard
        label="Return %"
        value={formatSignedPct(summary.return_pct)}
        tone={summary.return_pct >= 0 ? 'positive' : 'negative'}
      />
      <StatCard label="Portfolio Risk" value={<RiskBadge risk={summary.portfolio_risk} />} />
      <StatCard label="Health Score" value={`${summary.health_score.toFixed(0)} / 100`} />
    </div>
  );
}

function AiMarketOutlookSection({ holdings }: { holdings: Holding[] | null }) {
  const [predictions, setPredictions] = useState<Record<string, Prediction>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!holdings) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.allSettled(holdings.map((h) => stockService.getPrediction(h.symbol))).then((results) => {
      if (cancelled) return;
      const map: Record<string, Prediction> = {};
      let anySuccess = false;
      results.forEach((r, i) => {
        if (r.status === 'fulfilled') {
          map[holdings[i].symbol] = r.value;
          anySuccess = true;
        }
      });
      setPredictions(map);
      if (!anySuccess && holdings.length > 0) {
        setError('Unable to load AI predictions for your holdings right now.');
      }
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [holdings]);

  return (
    <Card title="AI Market Outlook" subtitle="Model-generated directional estimates for each current holding">
      {!holdings && <LoadingBlock />}
      {holdings && holdings.length === 0 && (
        <EmptyBlock title="No holdings to analyze" message="Add stocks to your portfolio to see AI market outlook." />
      )}
      {holdings && holdings.length > 0 && loading && <LoadingBlock label="Fetching model predictions…" />}
      {holdings && holdings.length > 0 && !loading && error && Object.keys(predictions).length === 0 && (
        <ErrorBlock message={error} />
      )}
      {holdings && holdings.length > 0 && !loading && Object.keys(predictions).length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {holdings.map((h) =>
            predictions[h.symbol] ? <PredictionCard key={h.symbol} symbol={h.symbol} prediction={predictions[h.symbol]} /> : null
          )}
        </div>
      )}
    </Card>
  );
}

function IntelligenceSummary({
  healthData,
  healthLoading,
  healthError,
  onHealthRetry,
  weaknessesData,
  weaknessesLoading,
  weaknessesError,
  onWeaknessesRetry,
}: {
  healthData: import('../types/api').PortfolioHealth | null;
  healthLoading: boolean;
  healthError: string | null;
  onHealthRetry: () => void;
  weaknessesData: Weakness[] | null;
  weaknessesLoading: boolean;
  weaknessesError: string | null;
  onWeaknessesRetry: () => void;
}) {
  if (healthLoading || weaknessesLoading) return <LoadingBlock />;
  if (healthError) return <ErrorBlock message={healthError} onRetry={onHealthRetry} />;
  if (weaknessesError) return <ErrorBlock message={weaknessesError} onRetry={onWeaknessesRetry} />;
  if (!healthData) return null;

  const diversification = healthData.components.find((c) => c.name === 'Diversification');
  const concentration = healthData.components.find((c) => c.name === 'Concentration');
  const risk = healthData.components.find((c) => c.name === 'Risk');

  const sortedWeaknesses = [...(weaknessesData ?? [])].sort((a, b) => severityRank(b.severity) - severityRank(a.severity));
  const mainWeakness = sortedWeaknesses[0];

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MiniStat label="Health Score" value={`${healthData.overall_health.toFixed(0)} / 100`} />
        <MiniStat
          label="Diversification"
          value={diversification ? `${diversification.score.toFixed(0)} / 100` : '—'}
          hint={diversification?.description}
        />
        <MiniStat
          label="Concentration"
          value={concentration ? `${concentration.score.toFixed(0)} / 100` : '—'}
          hint={concentration?.description}
        />
        <MiniStat label="Risk Score" value={risk ? `${risk.score.toFixed(0)} / 100` : '—'} hint={risk?.description} />
      </div>

      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Main Observation</p>
        {mainWeakness ? (
          <WeaknessCard weakness={mainWeakness} />
        ) : (
          <EmptyBlock tone="positive" title="No major weaknesses detected" message="Your portfolio currently shows no significant concentration, correlation, or risk concerns." />
        )}
      </div>
    </div>
  );
}

function severityRank(s: string): number {
  if (s === 'HIGH') return 3;
  if (s === 'MEDIUM') return 2;
  return 1;
}

function MiniStat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-base-border bg-base-surface2 p-3" title={hint}>
      <p className="text-[11px] uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-base font-bold text-slate-100">{value}</p>
    </div>
  );
}

function RecentNewsSection({ holdings }: { holdings: Holding[] | null }) {
  const [news, setNews] = useState<NewsItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!holdings) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.allSettled(holdings.map((h) => stockService.getNews(h.symbol, 10)))
      .then((results) => {
        if (cancelled) return;
        const merged: NewsItem[] = [];
        let anySuccess = false;
        results.forEach((r, i) => {
          if (r.status === 'fulfilled') {
            anySuccess = true;
            r.value.forEach((n) => merged.push({ ...n, symbol: holdings[i].symbol }));
          }
        });
        merged.sort((a, b) => new Date(b.published_at).getTime() - new Date(a.published_at).getTime());
        setNews(merged.slice(0, 10));
        if (!anySuccess && holdings.length > 0) setError(getErrorMessage(new Error('Unable to load news right now.')));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [holdings]);

  return (
    <Card title="Recent Financial News" subtitle="Latest headlines across your holdings, sorted by publish time">
      {!holdings && <LoadingBlock />}
      {holdings && holdings.length === 0 && <EmptyBlock title="No news to show" message="Add holdings to see relevant financial news." />}
      {holdings && holdings.length > 0 && loading && <LoadingBlock label="Fetching latest news…" />}
      {holdings && holdings.length > 0 && !loading && error && (!news || news.length === 0) && <ErrorBlock message={error} />}
      {holdings && holdings.length > 0 && !loading && news && news.length > 0 && (
        <div className="divide-y divide-base-border">
          {news.map((item) => (
            <NewsRow key={`${item.symbol}-${item.id}`} item={item} />
          ))}
        </div>
      )}
      {holdings && holdings.length > 0 && !loading && news && news.length === 0 && !error && (
        <EmptyBlock title="No recent news" message="No news articles found for your current holdings." />
      )}
    </Card>
  );
}
