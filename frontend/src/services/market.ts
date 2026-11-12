import { api } from './api';
import type { CandlesOut, MarketStatusOut, RegimeOut } from '../types/api';

export async function getMarketStatus(): Promise<MarketStatusOut> {
  const res = await api.get<MarketStatusOut>('/market/status');
  return res.data;
}

export async function getCandles(symbol: string, limit = 390): Promise<CandlesOut> {
  const res = await api.get<CandlesOut>(`/market/candles/${symbol}`, { params: { limit } });
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
