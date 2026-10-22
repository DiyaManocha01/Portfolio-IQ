import { describe, it, expect } from 'vitest';
import {
  formatCurrency,
  formatNumber,
  formatPct,
  formatSignedPct,
  formatProbabilityPct,
  formatVolume,
  formatDate,
  timeAgo,
} from './format';

describe('formatCurrency', () => {
  it('formats a positive amount as INR', () => {
    expect(formatCurrency(1234.5)).toBe('₹1,234.50');
  });

  it('returns an em dash for null/undefined/NaN', () => {
    expect(formatCurrency(null)).toBe('—');
    expect(formatCurrency(undefined)).toBe('—');
    expect(formatCurrency(NaN)).toBe('—');
  });

  it('compacts large positive values into Lakh/Crore notation', () => {
    expect(formatCurrency(150000, { compact: true })).toBe('₹1.50L');
    expect(formatCurrency(25000000, { compact: true })).toBe('₹2.50Cr');
    expect(formatCurrency(2500, { compact: true })).toBe('₹2.5K');
  });

  it('compacts negative values with a leading sign', () => {
    expect(formatCurrency(-150000, { compact: true })).toBe('-₹1.50L');
  });
});

describe('formatNumber', () => {
  it('formats with the default 2 digits', () => {
    expect(formatNumber(1234.5678)).toBe('1,234.57');
  });

  it('respects a custom digit count', () => {
    expect(formatNumber(1.23456, 3)).toBe('1.235');
  });

  it('returns an em dash for null/undefined/NaN', () => {
    expect(formatNumber(null)).toBe('—');
    expect(formatNumber(undefined)).toBe('—');
    expect(formatNumber(NaN)).toBe('—');
  });
});

describe('formatPct', () => {
  it('appends a percent sign with default 2 digits', () => {
    expect(formatPct(12.345)).toBe('12.35%');
  });

  it('does not add a leading + for positive values', () => {
    expect(formatPct(5)).toBe('5.00%');
  });

  it('returns an em dash for null/undefined/NaN', () => {
    expect(formatPct(null)).toBe('—');
  });
});

describe('formatSignedPct', () => {
  it('adds a + sign for positive values', () => {
    expect(formatSignedPct(5.5)).toBe('+5.50%');
  });

  it('keeps the - sign for negative values without duplicating it', () => {
    expect(formatSignedPct(-5.5)).toBe('-5.50%');
  });

  it('adds no sign for exactly zero', () => {
    expect(formatSignedPct(0)).toBe('0.00%');
  });

  it('returns an em dash for null/undefined/NaN', () => {
    expect(formatSignedPct(undefined)).toBe('—');
  });
});

describe('formatProbabilityPct', () => {
  it('multiplies by 100 and defaults to 0 digits', () => {
    expect(formatProbabilityPct(0.2)).toBe('20%');
  });

  it('respects a custom digit count', () => {
    expect(formatProbabilityPct(0.236, 1)).toBe('23.6%');
  });

  it('returns an em dash for null/undefined/NaN', () => {
    expect(formatProbabilityPct(null)).toBe('—');
  });
});

describe('formatVolume', () => {
  it('compacts volumes into Lakh/Crore notation without a currency symbol', () => {
    expect(formatVolume(150000)).toBe('1.50L');
    expect(formatVolume(25000000)).toBe('2.50Cr');
    expect(formatVolume(500)).toBe('500');
  });

  it('returns an em dash for null/undefined/NaN', () => {
    expect(formatVolume(null)).toBe('—');
  });
});

describe('formatDate', () => {
  it('formats an ISO date string', () => {
    expect(formatDate('2026-01-15')).toBe('15 Jan 2026');
  });

  it('returns an em dash for a falsy value', () => {
    expect(formatDate(null)).toBe('—');
    expect(formatDate(undefined)).toBe('—');
    expect(formatDate('')).toBe('—');
  });

  it('returns the raw string for an unparseable value', () => {
    expect(formatDate('not-a-date')).toBe('not-a-date');
  });
});

describe('timeAgo', () => {
  it('reports "just now" for the current instant', () => {
    expect(timeAgo(new Date().toISOString())).toBe('just now');
  });

  it('reports minutes ago for a recent timestamp', () => {
    const tenMinAgo = new Date(Date.now() - 10 * 60 * 1000).toISOString();
    expect(timeAgo(tenMinAgo)).toBe('10m ago');
  });

  it('falls back to a formatted date for values 30+ days old', () => {
    const old = new Date('2020-01-01T00:00:00Z').toISOString();
    expect(timeAgo(old)).toBe(formatDate(old));
  });

  it('returns an em dash for a falsy value', () => {
    expect(timeAgo(null)).toBe('—');
  });
});
