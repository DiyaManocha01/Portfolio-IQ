import { api } from './api';
import type { DiscoverItem, PortfolioFit } from '../types/api';

export async function getDiscover(limit = 20): Promise<DiscoverItem[]> {
  const res = await api.get<DiscoverItem[]>('/discover', { params: { limit } });
  return res.data;
}

export async function getPortfolioFit(symbol: string): Promise<PortfolioFit> {
  const res = await api.get<PortfolioFit>(`/portfolio-fit/${symbol}`);
  return res.data;
}
