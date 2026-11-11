import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAsync } from '../hooks/useAsync';
import * as alertService from '../services/alerts';
import { Card } from '../components/Card';
import { Badge } from '../components/Badge';
import { ErrorBlock, LoadingBlock, EmptyBlock } from '../components/States';
import { formatDateTime, timeAgo } from '../utils/format';
import type { AlertDirection, AlertRuleOut, AlertRuleType } from '../types/api';

const RULE_TYPE_META: Record<AlertRuleType, { label: string; needsSymbol: boolean; needsDirection: boolean; thresholdLabel: string }> = {
  PRICE_THRESHOLD: { label: 'Price Threshold', needsSymbol: true, needsDirection: true, thresholdLabel: 'Price (₹)' },
  PRICE_PCT_MOVE: { label: 'Daily % Move', needsSymbol: true, needsDirection: false, thresholdLabel: '% Move Magnitude' },
  VOLUME_SPIKE: { label: 'Volume Spike', needsSymbol: true, needsDirection: false, thresholdLabel: 'Multiple of 20d Avg (e.g. 2 = 2x)' },
  RSI_THRESHOLD: { label: 'RSI Threshold', needsSymbol: true, needsDirection: true, thresholdLabel: 'RSI Level' },
  SENTIMENT_CHANGE: { label: 'Sentiment Change', needsSymbol: true, needsDirection: false, thresholdLabel: 'Score Delta' },
  PORTFOLIO_VOLATILITY_CHANGE: { label: 'Portfolio Volatility Change', needsSymbol: false, needsDirection: false, thresholdLabel: 'Change (percentage points)' },
  SECTOR_CONCENTRATION_CHANGE: { label: 'Sector Concentration Change', needsSymbol: false, needsDirection: false, thresholdLabel: 'Change (percentage points)' },
  FIT_RANKING_CHANGE: { label: 'Portfolio Fit Score Change', needsSymbol: true, needsDirection: false, thresholdLabel: 'Fit Score Points' },
};

const RULE_TYPES = Object.keys(RULE_TYPE_META) as AlertRuleType[];

export default function AlertsPage() {
  const rules = useAsync(() => alertService.listRules(), []);
  const events = useAsync(() => alertService.listEvents(), []);
  const [evaluating, setEvaluating] = useState(false);

  async function handleEvaluateNow() {
    setEvaluating(true);
    try {
      await alertService.evaluateRules();
      rules.reload();
      events.reload();
    } finally {
      setEvaluating(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Alerts</h1>
          <p className="mt-1 text-sm text-slate-400">
            Configurable alerts for price, volume, RSI, sentiment, and portfolio-level changes. Every alert explains
            the event that triggered it.
          </p>
        </div>
        <button
          onClick={handleEvaluateNow}
          disabled={evaluating}
          className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-500 transition disabled:opacity-50"
        >
          {evaluating ? 'Checking…' : 'Check Now'}
        </button>
      </div>

      <NewRuleForm onCreated={() => rules.reload()} />

      <Card title="Your Rules">
        {rules.loading && <LoadingBlock />}
        {rules.error && <ErrorBlock message={rules.error} onRetry={rules.reload} />}
        {rules.data && rules.data.length === 0 && (
          <EmptyBlock title="No alert rules yet" message="Create one above to get started." />
        )}
        {rules.data && rules.data.length > 0 && (
          <RulesList rules={rules.data} onChanged={() => rules.reload()} />
        )}
      </Card>

      <Card title="Recent Alerts">
        {events.loading && <LoadingBlock />}
        {events.error && <ErrorBlock message={events.error} onRetry={events.reload} />}
        {events.data && events.data.length === 0 && (
          <EmptyBlock title="No alerts yet" message="Triggered alerts will show up here with an explanation of what happened." />
        )}
        {events.data && events.data.length > 0 && (
          <ul className="divide-y divide-base-border">
            {events.data.map((e) => (
              <li key={e.id} className="flex items-start justify-between gap-4 py-3">
                <div className="min-w-0">
                  <p className="text-sm text-slate-100">{e.message}</p>
                  <div className="mt-1 flex items-center gap-2 text-xs text-slate-500">
                    {e.symbol && (
                      <Link to={`/stocks/${e.symbol}`} className="hover:text-brand-300">
                        {e.symbol}
                      </Link>
                    )}
                    <span>{timeAgo(e.triggered_at)}</span>
                  </div>
                </div>
                {!e.is_read && (
                  <button
                    onClick={() => alertService.markEventRead(e.id).then(() => events.reload())}
                    className="shrink-0 rounded-full border border-base-border px-2.5 py-0.5 text-[11px] font-medium text-slate-400 hover:bg-base-surface2"
                  >
                    Mark read
                  </button>
                )}
                {e.is_read && <Badge tone="neutral">Read</Badge>}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function NewRuleForm({ onCreated }: { onCreated: () => void }) {
  const [ruleType, setRuleType] = useState<AlertRuleType>('PRICE_THRESHOLD');
  const [symbol, setSymbol] = useState('');
  const [direction, setDirection] = useState<AlertDirection>('ABOVE');
  const [threshold, setThreshold] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const meta = RULE_TYPE_META[ruleType];

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const parsedThreshold = Number(threshold);
    if (Number.isNaN(parsedThreshold)) {
      setError('Enter a valid threshold.');
      return;
    }
    setSubmitting(true);
    try {
      await alertService.createRule({
        rule_type: ruleType,
        symbol: meta.needsSymbol ? symbol.toUpperCase() : undefined,
        direction: meta.needsDirection ? direction : undefined,
        threshold: parsedThreshold,
      });
      setSymbol('');
      setThreshold('');
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create the rule.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card title="New Alert Rule">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <label htmlFor="alert-type" className="mb-1 block text-xs font-medium text-slate-400">
              Alert Type
            </label>
            <select
              id="alert-type"
              value={ruleType}
              onChange={(e) => setRuleType(e.target.value as AlertRuleType)}
              className="w-full rounded-lg border border-base-border bg-base-surface2 px-3 py-2 text-sm text-slate-100 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
            >
              {RULE_TYPES.map((rt) => (
                <option key={rt} value={rt}>
                  {RULE_TYPE_META[rt].label}
                </option>
              ))}
            </select>
          </div>

          {meta.needsSymbol && (
            <div>
              <label htmlFor="alert-symbol" className="mb-1 block text-xs font-medium text-slate-400">
                Symbol
              </label>
              <input
                id="alert-symbol"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                placeholder="e.g. TCS"
                required
                className="w-full rounded-lg border border-base-border bg-base-surface2 px-3 py-2 text-sm text-slate-100 placeholder-slate-600 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
              />
            </div>
          )}

          {meta.needsDirection && (
            <div>
              <label htmlFor="alert-direction" className="mb-1 block text-xs font-medium text-slate-400">
                Direction
              </label>
              <select
                id="alert-direction"
                value={direction}
                onChange={(e) => setDirection(e.target.value as AlertDirection)}
                className="w-full rounded-lg border border-base-border bg-base-surface2 px-3 py-2 text-sm text-slate-100 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
              >
                <option value="ABOVE">Above</option>
                <option value="BELOW">Below</option>
              </select>
            </div>
          )}

          <div>
            <label htmlFor="alert-threshold" className="mb-1 block text-xs font-medium text-slate-400">
              {meta.thresholdLabel}
            </label>
            <input
              id="alert-threshold"
              type="number"
              step="any"
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
              required
              className="w-full rounded-lg border border-base-border bg-base-surface2 px-3 py-2 text-sm text-slate-100 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
            />
          </div>
        </div>

        {error && <p className="text-xs text-negative">{error}</p>}

        <button
          type="submit"
          disabled={submitting}
          className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-500 transition disabled:opacity-50"
        >
          {submitting ? 'Creating…' : 'Create Rule'}
        </button>
      </form>
    </Card>
  );
}

function RulesList({ rules, onChanged }: { rules: AlertRuleOut[]; onChanged: () => void }) {
  return (
    <ul className="divide-y divide-base-border">
      {rules.map((r) => (
        <li key={r.id} className="flex items-center justify-between gap-4 py-3">
          <div className="min-w-0">
            <p className="text-sm font-medium text-slate-100">
              {RULE_TYPE_META[r.rule_type].label}
              {r.symbol && ` — ${r.symbol}`}
            </p>
            <p className="mt-0.5 text-xs text-slate-500">
              Threshold: {r.threshold}
              {r.direction ? ` (${r.direction.toLowerCase()})` : ''}
              {r.last_evaluated_at && ` · last checked ${timeAgo(r.last_evaluated_at)}`}
              {r.last_fired_at && ` · last fired ${formatDateTime(r.last_fired_at)}`}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Badge tone={r.enabled ? 'positive' : 'neutral'}>{r.enabled ? 'Enabled' : 'Disabled'}</Badge>
            <button
              onClick={() => alertService.updateRule(r.id, { enabled: !r.enabled }).then(onChanged)}
              className="rounded-full border border-base-border px-2.5 py-0.5 text-[11px] font-medium text-slate-400 hover:bg-base-surface2"
            >
              {r.enabled ? 'Disable' : 'Enable'}
            </button>
            <button
              onClick={() => alertService.deleteRule(r.id).then(onChanged)}
              className="rounded-full border border-negative/30 px-2.5 py-0.5 text-[11px] font-medium text-negative hover:bg-negative/10"
            >
              Delete
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}
