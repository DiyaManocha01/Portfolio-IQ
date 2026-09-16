import { FormEvent, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { getErrorMessage } from '../services/api';
import { AuthShell } from './AuthShell';

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (password.length < 6) {
      setError('Password must be at least 6 characters.');
      return;
    }
    setSubmitting(true);
    try {
      await register(email, password, fullName);
      navigate('/dashboard');
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthShell title="Create your account" subtitle="Set up PortfolioIQ to start tracking your portfolio's intelligence.">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-400">Full name</label>
          <input
            type="text"
            required
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            className="w-full rounded-lg border border-base-border bg-base-surface2 px-3 py-2.5 text-sm text-slate-100 placeholder-slate-600 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
            placeholder="Jane Investor"
          />
        </div>
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
            minLength={6}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-lg border border-base-border bg-base-surface2 px-3 py-2.5 text-sm text-slate-100 placeholder-slate-600 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
            placeholder="At least 6 characters"
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
          {submitting ? 'Creating account…' : 'Create account'}
        </button>
      </form>

      <p className="mt-6 text-center text-xs text-slate-500">
        Already have an account?{' '}
        <Link to="/login" className="font-medium text-brand-400 hover:text-brand-300">
          Log in
        </Link>
      </p>
    </AuthShell>
  );
}
