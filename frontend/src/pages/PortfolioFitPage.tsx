import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAsync } from '../hooks/useAsync';
import * as discoverService from '../services/discover';
import * as stockService from '../services/stocks';
import { Card } from '../components/Card';
import { ErrorBlock, LoadingBlock } from '../components/States';
import { HorizontalBarChart } from '../charts/HorizontalBarChart';
import { colorForIndex } from '../charts/palette';
import { getErrorMessage } from '../services/api';
import type { FitCounterfactual, FitRankingGap } from '../types/api';

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

          <CompareSection symbol={fit.data.symbol} />
          <CounterfactualSection symbol={fit.data.symbol} />
        </>
      )}
    </div>
  );
}

function CompareSection({ symbol }: { symbol: string }) {
  const stocks = useAsync(() => stockService.getStocks(), []);
  const [otherSymbol, setOtherSymbol] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<FitRankingGap | null>(null);

  async function handleCompare() {
    if (!otherSymbol) return;
    setLoading(true);
    setError(null);
    try {
      const r = await discoverService.compareFit(symbol, otherSymbol);
      setResult(r);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card title="Compare to Another Stock" subtitle="See which fit factors explain the score gap between two candidates">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-400">Compare against</label>
          {stocks.data && (
            <select
              value={otherSymbol}
              onChange={(e) => setOtherSymbol(e.target.value)}
              className="rounded-lg border border-base-border bg-base-surface2 px-3 py-2 text-sm text-slate-100 outline-none focus:border-brand-500"
            >
              <option value="">Select a stock…</option>
              {stocks.data
                .filter((s) => s.symbol !== symbol)
                .map((s) => (
                  <option key={s.symbol} value={s.symbol}>
                    {s.symbol} — {s.name}
                  </option>
                ))}
            </select>
          )}
        </div>
        <button
          onClick={handleCompare}
          disabled={!otherSymbol || loading}
          className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-60"
        >
          {loading ? 'Comparing…' : 'Compare'}
        </button>
      </div>

      {error && (
        <div className="mt-4">
          <ErrorBlock message={error} onRetry={handleCompare} />
        </div>
      )}

      {result && (
        <div className="mt-5 space-y-4">
          <div className="flex items-center gap-6">
            <div>
              <p className="text-xs text-slate-500">{result.symbol_a}</p>
              <p className="text-2xl font-bold text-brand-400">{result.fit_score_a.toFixed(1)}</p>
            </div>
            <div className="text-slate-500">vs.</div>
            <div>
              <p className="text-xs text-slate-500">{result.symbol_b}</p>
              <p className="text-2xl font-bold text-slate-300">{result.fit_score_b.toFixed(1)}</p>
            </div>
          </div>

          {result.term_deltas.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[480px] text-sm">
                <thead>
                  <tr className="border-b border-base-border text-left text-xs uppercase tracking-wide text-slate-500">
                    <th className="pb-2 pr-3 font-medium">Factor</th>
                    <th className="pb-2 pr-3 font-medium text-right">{result.symbol_a}</th>
                    <th className="pb-2 pr-3 font-medium text-right">{result.symbol_b}</th>
                    <th className="pb-2 pr-3 font-medium text-right">Delta</th>
                  </tr>
                </thead>
                <tbody>
                  {result.term_deltas.map((t) => (
                    <tr key={t.term} className="border-b border-base-border/60 last:border-0">
                      <td className="py-2.5 pr-3 text-slate-200">{t.name}</td>
                      <td className="py-2.5 pr-3 text-right text-slate-300">{t.contribution_a.toFixed(2)}</td>
                      <td className="py-2.5 pr-3 text-right text-slate-300">{t.contribution_b.toFixed(2)}</td>
                      <td className={`py-2.5 pr-3 text-right font-semibold ${t.delta >= 0 ? 'text-positive' : 'text-negative'}`}>
                        {t.delta >= 0 ? '+' : ''}
                        {t.delta.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <p className="text-[11px] text-slate-500">{result.note}</p>
        </div>
      )}
    </Card>
  );
}

function CounterfactualSection({ symbol }: { symbol: string }) {
  const stocks = useAsync(() => stockService.getStocks(), []);
  const [mode, setMode] = useState<'symbol' | 'score'>('symbol');
  const [targetSymbol, setTargetSymbol] = useState('');
  const [targetScore, setTargetScore] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<FitCounterfactual | null>(null);

  async function handleRun() {
    setError(null);
    if (mode === 'symbol') {
      if (!targetSymbol) {
        setError('Choose a target stock to match.');
        return;
      }
    } else {
      const score = Number(targetScore);
      if (!targetScore || Number.isNaN(score)) {
        setError('Enter a valid target fit score.');
        return;
      }
    }
    setLoading(true);
    try {
      const r =
        mode === 'symbol'
          ? await discoverService.getFitCounterfactual(symbol, { targetSymbol })
          : await discoverService.getFitCounterfactual(symbol, { targetScore: Number(targetScore) });
      setResult(r);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card
      title="What Would Improve This Fit?"
      subtitle="Ceteris-paribus scenarios: how much a single factor would need to change, holding all others fixed"
    >
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex gap-2">
          <button
            onClick={() => setMode('symbol')}
            className={`rounded-lg px-3 py-2 text-xs font-medium transition ${
              mode === 'symbol' ? 'bg-brand-600 text-white' : 'bg-base-surface2 text-slate-400'
            }`}
          >
            Match another stock
          </button>
          <button
            onClick={() => setMode('score')}
            className={`rounded-lg px-3 py-2 text-xs font-medium transition ${
              mode === 'score' ? 'bg-brand-600 text-white' : 'bg-base-surface2 text-slate-400'
            }`}
          >
            Reach a target score
          </button>
        </div>

        {mode === 'symbol' && stocks.data && (
          <select
            value={targetSymbol}
            onChange={(e) => setTargetSymbol(e.target.value)}
            className="rounded-lg border border-base-border bg-base-surface2 px-3 py-2 text-sm text-slate-100 outline-none focus:border-brand-500"
          >
            <option value="">Select a stock…</option>
            {stocks.data
              .filter((s) => s.symbol !== symbol)
              .map((s) => (
                <option key={s.symbol} value={s.symbol}>
                  {s.symbol} — {s.name}
                </option>
              ))}
          </select>
        )}

        {mode === 'score' && (
          <input
            type="number"
            min="0"
            max="100"
            step="any"
            placeholder="e.g. 75"
            value={targetScore}
            onChange={(e) => setTargetScore(e.target.value)}
            className="w-28 rounded-lg border border-base-border bg-base-surface2 px-3 py-2 text-sm text-slate-100 outline-none focus:border-brand-500"
          />
        )}

        <button
          onClick={handleRun}
          disabled={loading}
          className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-60"
        >
          {loading ? 'Computing…' : 'Run'}
        </button>
      </div>

      {error && (
        <div className="mt-4">
          <ErrorBlock message={error} onRetry={handleRun} />
        </div>
      )}

      {result && (
        <div className="mt-5 space-y-4">
          {result.already_meets_target ? (
            <p className="rounded-lg border border-positive/30 bg-positive-bg px-3 py-2 text-sm text-positive">
              {symbol} already meets the target ({result.target}).
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-sm">
                <thead>
                  <tr className="border-b border-base-border text-left text-xs uppercase tracking-wide text-slate-500">
                    <th className="pb-2 pr-3 font-medium">Factor</th>
                    <th className="pb-2 pr-3 font-medium text-right">Current</th>
                    <th className="pb-2 pr-3 font-medium text-right">Required Change (z)</th>
                    <th className="pb-2 pr-3 font-medium text-right">Target Value</th>
                  </tr>
                </thead>
                <tbody>
                  {result.term_scenarios.map((s) => (
                    <tr key={s.term} className="border-b border-base-border/60 last:border-0">
                      <td className="py-2.5 pr-3 text-slate-200">{s.name}</td>
                      <td className="py-2.5 pr-3 text-right text-slate-300">{s.current_raw_value.toFixed(2)}</td>
                      <td className="py-2.5 pr-3 text-right text-slate-300">
                        {s.required_z_delta >= 0 ? '+' : ''}
                        {s.required_z_delta.toFixed(2)}
                      </td>
                      <td className="py-2.5 pr-3 text-right font-semibold text-brand-400">
                        {s.target_raw_value !== null ? s.target_raw_value.toFixed(2) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="text-[11px] text-slate-500">{result.note}</p>
        </div>
      )}
    </Card>
  );
}
