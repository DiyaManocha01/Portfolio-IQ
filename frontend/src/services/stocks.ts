import { api } from './api';
import type {
  StockListItem,
  StockDetail,
  StockHistory,
  Prediction,
  NewsItem,
  SentimentSummary,
} from '../types/api';

export async function getStocks(): Promise<StockListItem[]> {
  const res = await api.get<StockListItem[]>('/stocks');
  return res.data;
}

export async function getStockDetail(symbol: string): Promise<StockDetail> {
  const res = await api.get<StockDetail>(`/stocks/${symbol}`);
  return res.data;
}

export async function getStockHistory(symbol: string, days = 200): Promise<StockHistory> {
  const res = await api.get<StockHistory>(`/stocks/${symbol}/history`, { params: { days } });
  return res.data;
}

export async function getPrediction(symbol: string): Promise<Prediction> {
  const res = await api.get<Prediction>(`/stocks/${symbol}/prediction`);
  return res.data;
}

export async function getNews(symbol: string, limit = 10): Promise<NewsItem[]> {
  const res = await api.get<NewsItem[]>(`/stocks/${symbol}/news`, { params: { limit } });
  return res.data;
}

export async function getSentiment(symbol: string): Promise<SentimentSummary> {
  const res = await api.get<SentimentSummary>(`/stocks/${symbol}/sentiment`);
  return res.data;
}
