import { api } from './api';
import type { DiscoverItem, FitCounterfactual, FitRankingGap, PortfolioFit } from '../types/api';

export async function getDiscover(limit = 20): Promise<DiscoverItem[]> {
  const res = await api.get<DiscoverItem[]>('/discover', { params: { limit } });
  return res.data;
}

export async function getPortfolioFit(symbol: string): Promise<PortfolioFit> {
  const res = await api.get<PortfolioFit>(`/portfolio-fit/${symbol}`);
  return res.data;
}

export async function compareFit(symbol: string, otherSymbol: string): Promise<FitRankingGap> {
  const res = await api.get<FitRankingGap>(`/portfolio-fit/${symbol}/compare/${otherSymbol}`);
  return res.data;
}

export async function getFitCounterfactual(
  symbol: string,
  target: { targetSymbol: string } | { targetScore: number }
): Promise<FitCounterfactual> {
  const params =
    'targetSymbol' in target ? { target_symbol: target.targetSymbol } : { target_score: target.targetScore };
  const res = await api.get<FitCounterfactual>(`/portfolio-fit/${symbol}/counterfactual`, { params });
  return res.data;
}
