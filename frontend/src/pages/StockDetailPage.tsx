import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import clsx from 'clsx';
import { useAsync } from '../hooks/useAsync';
import * as stockService from '../services/stocks';
import { Card } from '../components/Card';
import { StatCard } from '../components/StatCard';
import { ErrorBlock, LoadingBlock, EmptyBlock } from '../components/States';
import { ConfidenceBadge, DataSourceBadge, DirectionBadge, SentimentBadge } from '../components/Badge';
import { PriceHistoryChart } from '../charts/PriceHistoryChart';
import { formatCurrency, formatNumber, formatProbabilityPct, formatSignedPct, formatVolume, timeAgo } from '../utils/format';

type Tab = 'overview' | 'outlook' | 'news';

export default function StockDetailPage() {
  const { symbol = '' } = useParams();
  const [tab, setTab] = useState<Tab>('overview');

  const detail = useAsync(() => stockService.getStockDetail(symbol), [symbol]);
  const prediction = useAsync(() => stockService.getPrediction(symbol), [symbol]);
  const news = useAsync(() => stockService.getNews(symbol, 10), [symbol]);
  const sentiment = useAsync(() => stockService.getSentiment(symbol), [symbol]);

  return (
    <div className="space-y-6">
      <div>
        <Link to="/stocks" className="text-xs font-medium text-brand-400 hover:text-brand-300">
          &larr; Back to Stocks
        </Link>
        <h1 className="mt-2 text-2xl font-bold text-slate-100">{symbol}</h1>
        {detail.data && <p className="mt-1 text-sm text-slate-400">{detail.data.quote.name} &middot; {detail.data.quote.sector}</p>}
      </div>

      {detail.loading && <LoadingBlock />}
      {detail.error && <ErrorBlock message={detail.error} onRetry={detail.reload} />}

      {detail.data && (
        <>
          <QuoteRow quote={detail.data.quote} />

          <div className="flex gap-2 border-b border-base-border">
            {(['overview', 'outlook', 'news'] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={clsx(
                  'px-4 py-2.5 text-sm font-medium capitalize transition border-b-2 -mb-px',
                  tab === t ? 'border-brand-500 text-brand-300' : 'border-transparent text-slate-500 hover:text-slate-300'
                )}
              >
                {t === 'outlook' ? 'AI Outlook' : t}
              </button>
            ))}
          </div>

          {tab === 'overview' && <OverviewTab detail={detail.data} />}
          {tab === 'outlook' && (
            <OutlookTab
              prediction={prediction.data}
              loading={prediction.loading}
              error={prediction.error}
              onRetry={prediction.reload}
              symbol={symbol}
            />
          )}
          {tab === 'news' && (
            <NewsTab
              news={news.data}
              newsLoading={news.loading}
              newsError={news.error}
              onNewsRetry={news.reload}
              sentiment={sentiment.data}
              sentimentLoading={sentiment.loading}
              sentimentError={sentiment.error}
            />
          )}
        </>
      )}
    </div>
  );
}

function QuoteRow({ quote }: { quote: import('../types/api').StockQuote }) {
  const positive = quote.change >= 0;
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      <StatCard label="Current Price" value={formatCurrency(quote.current_price)} />
      <StatCard
        label="Daily Change"
        value={`${positive ? '+' : ''}${formatCurrency(quote.change)}`}
        tone={positive ? 'positive' : 'negative'}
        sub={formatSignedPct(quote.change_percent)}
      />
      <StatCard label="Previous Close" value={formatCurrency(quote.previous_close)} />
      <StatCard label="Volume" value={formatVolume(quote.volume)} sub={<DataSourceBadge source={quote.data_source} />} />
    </div>
  );
}

function OverviewTab({ detail }: { detail: import('../types/api').StockDetail }) {
  const { indicators, history } = detail;
  return (
    <div className="space-y-6">
      <Card title="Price History" subtitle="Historical closing price">
        {history.length > 0 ? (
          <PriceHistoryChart points={history} />
        ) : (
          <EmptyBlock title="No price history" message="Historical data is not available for this stock." />
        )}
      </Card>

      <Card title="Technical Indicators" subtitle="Computed from recent price and volume data">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          <IndicatorStat label="SMA 20" value={formatCurrency(indicators.sma_20)} />
          <IndicatorStat label="SMA 50" value={formatCurrency(indicators.sma_50)} />
          <IndicatorStat label="EMA 20" value={formatCurrency(indicators.ema_20)} />
          <IndicatorStat label="RSI (14)" value={formatNumber(indicators.rsi_14, 1)} />
          <IndicatorStat label="Volatility (Ann.)" value={formatProbabilityPct(indicators.volatility_annualized)} />
          <IndicatorStat label="Momentum (10d)" value={formatSignedPct(indicators.momentum_10d * 100)} />
          <IndicatorStat label="Daily Return" value={formatSignedPct(indicators.daily_return * 100)} />
          <IndicatorStat label="Cumulative Return (30d)" value={formatSignedPct(indicators.cumulative_return_30d * 100)} />
          <IndicatorStat label="Avg Volume (20d)" value={formatVolume(indicators.avg_volume_20d)} />
        </div>
      </Card>
    </div>
  );
}

function IndicatorStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-base-border bg-base-surface2 p-3">
      <p className="text-[11px] uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-sm font-bold text-slate-100">{value}</p>
    </div>
  );
}

function OutlookTab({
  prediction,
  loading,
  error,
  onRetry,
  symbol,
}: {
  prediction: import('../types/api').Prediction | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  symbol: string;
}) {
  if (loading) return <LoadingBlock />;
  if (error) return <ErrorBlock message={error} onRetry={onRetry} />;
  if (!prediction) return null;

  return (
    <Card title={`AI Stock Outlook — ${symbol}`} subtitle="Model-generated estimate, refreshed daily">
      <div className="flex flex-wrap items-center gap-4">
        <DirectionBadge direction={prediction.direction} />
        <ConfidenceBadge confidence={prediction.confidence} />
        <div>
          <span className="text-xs text-slate-500">Model Probability: </span>
          <span className="text-sm font-bold text-slate-100">{formatProbabilityPct(prediction.probability)}</span>
        </div>
        <div className="text-xs text-slate-500">Model: {prediction.model_name}</div>
      </div>

      {prediction.important_features.length > 0 && (
        <div className="mt-5">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Important Features</p>
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {prediction.important_features.map((f) => (
              <li key={f} className="rounded-lg border border-base-border bg-base-surface2 px-3 py-2 text-xs text-slate-300">
                {f}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-5 rounded-lg border border-base-border bg-base-surface2 px-3 py-2.5 text-xs italic text-slate-500">
        {prediction.disclaimer}
      </div>
    </Card>
  );
}

function NewsTab({
  news,
  newsLoading,
  newsError,
  onNewsRetry,
  sentiment,
  sentimentLoading,
  sentimentError,
}: {
  news: import('../types/api').NewsItem[] | null;
  newsLoading: boolean;
  newsError: string | null;
  onNewsRetry: () => void;
  sentiment: import('../types/api').SentimentSummary | null;
  sentimentLoading: boolean;
  sentimentError: string | null;
}) {
  return (
    <div className="space-y-6">
      <Card title="Sentiment Summary" subtitle="Aggregated across recent news articles">
        {sentimentLoading && <LoadingBlock />}
        {sentimentError && <ErrorBlock message={sentimentError} />}
        {sentiment && (
          <div className="space-y-3">
            <div className="flex h-3 w-full overflow-hidden rounded-full bg-base-surface2">
              <div style={{ width: `${sentiment.positive_pct}%` }} className="bg-positive" title={`Positive ${sentiment.positive_pct}%`} />
              <div style={{ width: `${sentiment.neutral_pct}%` }} className="bg-neutral" title={`Neutral ${sentiment.neutral_pct}%`} />
              <div style={{ width: `${sentiment.negative_pct}%` }} className="bg-negative" title={`Negative ${sentiment.negative_pct}%`} />
            </div>
            <div className="flex flex-wrap gap-4 text-xs text-slate-400">
              <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-positive" /> Positive {sentiment.positive_pct.toFixed(0)}%</span>
              <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-neutral" /> Neutral {sentiment.neutral_pct.toFixed(0)}%</span>
              <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-negative" /> Negative {sentiment.negative_pct.toFixed(0)}%</span>
              <span>Trend: <span className="font-medium text-slate-300">{sentiment.trend}</span></span>
              <span>{sentiment.article_count} articles analyzed</span>
            </div>
          </div>
        )}
      </Card>

      <Card title="Recent News">
        {newsLoading && <LoadingBlock />}
        {newsError && <ErrorBlock message={newsError} onRetry={onNewsRetry} />}
        {news && news.length === 0 && <EmptyBlock title="No recent news" message="No news articles found for this stock." />}
        {news && news.length > 0 && (
          <div className="divide-y divide-base-border">
            {news.map((n) => (
              <div key={n.id} className="flex items-start justify-between gap-4 py-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium leading-snug text-slate-100">{n.headline}</p>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                    <span>{n.source}</span>
                    <span>&middot;</span>
                    <span>{timeAgo(n.published_at)}</span>
                  </div>
                </div>
                <SentimentBadge label={n.sentiment_label} />
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
