// NOTE: We deliberately avoid Intl's `notation: 'compact'` for INR here.
// Some bundled Chromium/ICU builds mislabel the Indian-locale thousands
// suffix (observed rendering "T" instead of "K" for values like ₹3,900),
// so we compute the Lakh/Crore-based compact form explicitly instead.
export function formatCurrency(value: number | null | undefined, opts: { compact?: boolean } = {}): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  if (opts.compact) {
    const sign = value < 0 ? '-' : '';
    const abs = Math.abs(value);
    if (abs >= 1e7) return `${sign}₹${(abs / 1e7).toFixed(abs >= 1e8 ? 1 : 2)}Cr`;
    if (abs >= 1e5) return `${sign}₹${(abs / 1e5).toFixed(abs >= 1e6 ? 1 : 2)}L`;
    if (abs >= 1e3) return `${sign}₹${(abs / 1e3).toFixed(1)}K`;
    return `${sign}₹${abs.toFixed(0)}`;
  }
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: digits }).format(value);
}

export function formatPct(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${value >= 0 ? '' : ''}${value.toFixed(digits)}%`;
}

export function formatSignedPct(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(digits)}%`;
}

export function formatProbabilityPct(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${(value * 100).toFixed(digits)}%`;
}

// Same ICU-safety rationale as formatCurrency's compact path above.
export function formatVolume(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const abs = Math.abs(value);
  if (abs >= 1e7) return `${(abs / 1e7).toFixed(abs >= 1e8 ? 1 : 2)}Cr`;
  if (abs >= 1e5) return `${(abs / 1e5).toFixed(abs >= 1e6 ? 1 : 2)}L`;
  if (abs >= 1e3) return `${(abs / 1e3).toFixed(1)}K`;
  return `${Math.round(abs)}`;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function timeAgo(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  const diffMs = Date.now() - d.getTime();
  const diffMin = Math.round(diffMs / 60000);
  if (diffMin < 1) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.round(diffHr / 24);
  if (diffDay < 30) return `${diffDay}d ago`;
  return formatDate(value);
}
