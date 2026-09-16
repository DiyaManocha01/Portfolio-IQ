import { Link } from 'react-router-dom';
import { useAsync } from '../hooks/useAsync';
import * as discoverService from '../services/discover';
import { Card } from '../components/Card';
import { ErrorBlock, LoadingBlock, EmptyBlock } from '../components/States';
import { DirectionBadge, DiversificationBadge } from '../components/Badge';
import { formatCurrency, formatNumber, formatProbabilityPct } from '../utils/format';

export default function DiscoverPage() {
  const discover = useAsync(() => discoverService.getDiscover(20), []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Stocks That May Fit Your Portfolio</h1>
        <p className="mt-1 text-sm text-slate-400">
          Ranked by an estimated Portfolio Fit score that blends model outlook, risk, correlation, sector balance, and diversification benefit.
        </p>
      </div>

      {discover.loading && <LoadingBlock />}
      {discover.error && <ErrorBlock message={discover.error} onRetry={discover.reload} />}
      {discover.data && discover.data.length === 0 && (
        <EmptyBlock title="No candidates available" message="There are currently no unheld stocks to evaluate." />
      )}

      {discover.data && discover.data.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {discover.data.map((item) => (
            <Link key={item.symbol} to={`/discover/${item.symbol}`}>
              <Card className="h-full transition hover:border-brand-500/50 hover:shadow-lg">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-lg font-bold text-slate-100">{item.symbol}</p>
                    <p className="text-xs text-slate-400">{item.name}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-[10px] uppercase tracking-wide text-slate-500">Portfolio Fit</p>
                    <p className="text-2xl font-extrabold text-brand-400">{item.portfolio_fit.toFixed(0)}</p>
                  </div>
                </div>

                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <DirectionBadge direction={item.ml_outlook} />
                  <DiversificationBadge benefit={item.diversification_benefit} />
                </div>

                <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
                  <Metric label="Price" value={formatCurrency(item.current_price)} />
                  <Metric label="Sector" value={item.sector} />
                  <Metric label="Model Probability" value={formatProbabilityPct(item.prediction_probability)} />
                  <Metric label="Volatility" value={formatProbabilityPct(item.volatility)} />
                  <Metric label="Correlation w/ Portfolio" value={formatNumber(item.correlation_with_portfolio, 2)} />
                </div>

                <div className="mt-4 text-right text-xs font-medium text-brand-400">View fit breakdown &rarr;</div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wide text-slate-500">{label}</p>
      <p className="font-medium text-slate-200">{value}</p>
    </div>
  );
}
