import { api } from './api';
import type {
  Holding,
  PortfolioSummary,
  PortfolioPerformance,
  PortfolioAllocation,
  PortfolioRiskData,
  PortfolioHealth,
  PortfolioWeaknesses,
  PortfolioRiskAttribution,
  PortfolioOptimization,
  OptimizationMethod,
  WhatIfChange,
  WhatIfResult,
} from '../types/api';

export async function getHoldings(): Promise<Holding[]> {
  const res = await api.get<Holding[]>('/portfolio');
  return res.data;
}

export async function addHolding(symbol: string, quantity: number, avg_buy_price: number): Promise<Holding> {
  const res = await api.post<Holding>('/portfolio/holdings', { symbol, quantity, avg_buy_price });
  return res.data;
}

export async function removeHolding(holdingId: number): Promise<void> {
  await api.delete(`/portfolio/holdings/${holdingId}`);
}

export async function getSummary(): Promise<PortfolioSummary> {
  const res = await api.get<PortfolioSummary>('/portfolio/summary');
  return res.data;
}

export async function getPerformance(days = 180): Promise<PortfolioPerformance> {
  const res = await api.get<PortfolioPerformance>('/portfolio/performance', { params: { days } });
  return res.data;
}

export async function getAllocation(): Promise<PortfolioAllocation> {
  const res = await api.get<PortfolioAllocation>('/portfolio/allocation');
  return res.data;
}

export async function getRisk(): Promise<PortfolioRiskData> {
  const res = await api.get<PortfolioRiskData>('/portfolio/risk');
  return res.data;
}

export async function getHealth(): Promise<PortfolioHealth> {
  const res = await api.get<PortfolioHealth>('/portfolio/health');
  return res.data;
}

export async function getWeaknesses(): Promise<PortfolioWeaknesses> {
  const res = await api.get<PortfolioWeaknesses>('/portfolio/weaknesses');
  return res.data;
}

export async function getRiskAttribution(): Promise<PortfolioRiskAttribution> {
  const res = await api.get<PortfolioRiskAttribution>('/portfolio/risk-attribution');
  return res.data;
}

export async function getOptimization(method: OptimizationMethod): Promise<PortfolioOptimization> {
  const res = await api.get<PortfolioOptimization>('/portfolio/optimize', { params: { method } });
  return res.data;
}

export async function postWhatIf(changes: WhatIfChange[], includeCosts = true): Promise<WhatIfResult> {
  const res = await api.post<WhatIfResult>('/portfolio/what-if', { changes, include_costs: includeCosts });
  return res.data;
}
