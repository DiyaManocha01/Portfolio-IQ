import { api } from './api';
import type { PaperAccountOut, PaperHoldingOut, PaperPerformanceOut, PaperTransactionOut, TradeRequest } from '../types/api';

export async function getAccount(): Promise<PaperAccountOut> {
  const res = await api.get<PaperAccountOut>('/paper-trading/account');
  return res.data;
}

export async function resetAccount(): Promise<PaperAccountOut> {
  const res = await api.post<PaperAccountOut>('/paper-trading/account/reset');
  return res.data;
}

export async function buy(payload: TradeRequest): Promise<PaperTransactionOut> {
  const res = await api.post<PaperTransactionOut>('/paper-trading/buy', payload);
  return res.data;
}

export async function sell(payload: TradeRequest): Promise<PaperTransactionOut> {
  const res = await api.post<PaperTransactionOut>('/paper-trading/sell', payload);
  return res.data;
}

export async function listHoldings(): Promise<PaperHoldingOut[]> {
  const res = await api.get<PaperHoldingOut[]>('/paper-trading/holdings');
  return res.data;
}

export async function listTransactions(): Promise<PaperTransactionOut[]> {
  const res = await api.get<PaperTransactionOut[]>('/paper-trading/transactions');
  return res.data;
}

export async function getPerformance(days = 180): Promise<PaperPerformanceOut> {
  const res = await api.get<PaperPerformanceOut>('/paper-trading/performance', { params: { days } });
  return res.data;
}
