import { FormEvent, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { getErrorMessage } from '../services/api';
import { AuthShell } from './AuthShell';

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      navigate('/dashboard');
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  function fillDemo() {
    setEmail('demo@portfolioiq.app');
    setPassword('demo1234');
  }

  return (
    <AuthShell title="Welcome back" subtitle="Log in to view your AI-powered portfolio intelligence.">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-400">Email</label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-lg border border-base-border bg-base-surface2 px-3 py-2.5 text-sm text-slate-100 placeholder-slate-600 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
            placeholder="you@example.com"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-400">Password</label>
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-lg border border-base-border bg-base-surface2 px-3 py-2.5 text-sm text-slate-100 placeholder-slate-600 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
            placeholder="••••••••"
          />
        </div>

        {error && (
          <div className="rounded-lg border border-negative/30 bg-negative-bg px-3 py-2 text-xs text-negative">{error}</div>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-brand-600 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-60"
        >
          {submitting ? 'Logging in…' : 'Log in'}
        </button>
      </form>

      <div className="mt-4 rounded-lg border border-brand-500/30 bg-brand-500/10 px-3 py-2.5 text-center text-xs text-brand-300">
        Demo: <span className="font-semibold">demo@portfolioiq.app</span> / <span className="font-semibold">demo1234</span>
        <button type="button" onClick={fillDemo} className="ml-2 underline decoration-dotted underline-offset-2 hover:text-brand-200">
          autofill
        </button>
      </div>

      <p className="mt-6 text-center text-xs text-slate-500">
        Don&apos;t have an account?{' '}
        <Link to="/register" className="font-medium text-brand-400 hover:text-brand-300">
          Create one
        </Link>
      </p>
    </AuthShell>
  );
}
