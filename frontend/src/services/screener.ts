import { api } from './api';
import type { ScreenerFilters, ScreenerOut } from '../types/api';

export async function runScreener(filters: ScreenerFilters): Promise<ScreenerOut> {
  const res = await api.get<ScreenerOut>('/screener', { params: filters });
  return res.data;
}
