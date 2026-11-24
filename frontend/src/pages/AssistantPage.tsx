import { useState } from 'react';
import { Card } from '../components/Card';
import { Badge } from '../components/Badge';
import { askAssistant } from '../services/assistant';
import { getErrorMessage } from '../services/api';
import type { AssistantAnswer } from '../types/api';

interface ChatTurn {
  question: string;
  answer: AssistantAnswer;
}

export default function AssistantPage() {
  const [question, setQuestion] = useState('');
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || asking) return;
    setAsking(true);
    setError(null);
    try {
      const answer = await askAssistant(trimmed);
      setTurns((prev) => [...prev, { question: trimmed, answer }]);
      setQuestion('');
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setAsking(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">AI Portfolio Assistant</h1>
        <p className="mt-1 text-sm text-slate-400">
          Ask about your portfolio, holdings, risk, or market conditions. Every answer only cites data this app has
          already computed -- it never gives buy/sell advice or a guaranteed outcome.
        </p>
      </div>

      <Card>
        <div className="space-y-4">
          {turns.length === 0 && !asking && (
            <p className="py-6 text-center text-sm text-slate-500">
              No messages yet. Ask something like &quot;How is my portfolio doing today?&quot; or &quot;What's the
              sentiment on TCS?&quot;
            </p>
          )}

          {turns.map((turn, i) => (
            <div key={i} className="space-y-2">
              <div className="flex justify-end">
                <div className="max-w-[80%] rounded-xl bg-brand-600 px-4 py-2.5 text-sm text-white">{turn.question}</div>
              </div>
              <div className="flex justify-start">
                <div className="max-w-[80%] space-y-2 rounded-xl border border-base-border bg-base-surface2 px-4 py-2.5 text-sm text-slate-100">
                  <p className="whitespace-pre-wrap">{turn.answer.answer}</p>
                  {turn.answer.guardrail_tripped && (
                    <Badge tone="negative">
                      Guardrail: response adjusted{turn.answer.guardrail_matched_phrase ? ` (matched "${turn.answer.guardrail_matched_phrase}")` : ''}
                    </Badge>
                  )}
                  {turn.answer.sources_used.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {turn.answer.sources_used.map((s) => (
                        <Badge key={s} tone="neutral">
                          {s}
                        </Badge>
                      ))}
                    </div>
                  )}
                  <p className="pt-1 text-[11px] text-slate-500">{turn.answer.disclaimer}</p>
                </div>
              </div>
            </div>
          ))}

          {asking && (
            <div className="flex justify-start">
              <div className="flex items-center gap-2 rounded-xl border border-base-border bg-base-surface2 px-4 py-2.5 text-sm text-slate-400">
                <span className="h-2 w-2 animate-pulse rounded-full bg-brand-400" />
                Thinking…
              </div>
            </div>
          )}

          {error && <p className="text-xs text-negative">{error}</p>}
        </div>

        <form onSubmit={handleSubmit} className="mt-5 flex items-end gap-3 border-t border-base-border pt-4">
          <label htmlFor="assistant-question" className="sr-only">
            Ask the assistant a question
          </label>
          <textarea
            id="assistant-question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSubmit(e);
              }
            }}
            placeholder="Ask about your portfolio, a holding, risk, or market conditions…"
            rows={2}
            className="flex-1 resize-none rounded-lg border border-base-border bg-base-surface2 px-3 py-2 text-sm text-slate-100 placeholder-slate-600 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
          />
          <button
            type="submit"
            disabled={asking || !question.trim()}
            className="shrink-0 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-500 transition disabled:opacity-50"
          >
            {asking ? 'Asking…' : 'Ask'}
          </button>
        </form>
      </Card>
    </div>
  );
}
