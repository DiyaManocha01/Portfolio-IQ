import { api } from './api';
import type { CandlesOut, MarketIndicesOut, MarketMoversOut, MarketStatusOut, RegimeOut } from '../types/api';

export async function getMarketStatus(): Promise<MarketStatusOut> {
  const res = await api.get<MarketStatusOut>('/market/status');
  return res.data;
}

export async function getCandles(symbol: string, limit = 390): Promise<CandlesOut> {
  const res = await api.get<CandlesOut>(`/market/candles/${symbol}`, { params: { limit } });
  return res.data;
}

/** Real-data upgrade Phase E: gainers/losers/volume leaders/unusual volume/
 * 52-week high-low proximity, computed from the tracked watchlist only
 * (see `universe_scope` on the response). */
export async function getMovers(topN = 5): Promise<MarketMoversOut> {
  const res = await api.get<MarketMoversOut>('/market/movers', { params: { top_n: topN } });
  return res.data;
}

/** Real-data upgrade Phase E: NIFTY 50 / NIFTY BANK / NIFTY IT overview
 * tiles. SENSEX is reported in `unsupported` -- see docs/limitations.md. */
export async function getIndices(): Promise<MarketIndicesOut> {
  const res = await api.get<MarketIndicesOut>('/market/indices');
  return res.data;
}

/** Omit `symbol` for the NIFTY 50 market-wide regime. */
export async function getRegime(symbol?: string): Promise<RegimeOut> {
  const res = await api.get<RegimeOut>('/market/regime', { params: symbol ? { symbol } : {} });
  return res.data;
}

/** Derives the /ws/market URL from the same base URL axios is configured with. */
export function buildMarketWsUrl(token: string): string {
  const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
  const wsBase = baseURL.replace(/^https:/, 'wss:').replace(/^http:/, 'ws:');
  return `${wsBase}/ws/market?token=${encodeURIComponent(token)}`;
}
