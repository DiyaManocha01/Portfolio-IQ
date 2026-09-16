// Types mirrored from docs/API_CONTRACT.md

export interface User {
  id: number;
  email: string;
  full_name: string;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface Holding {
  id: number;
  symbol: string;
  name: string;
  sector: string;
  quantity: number;
  avg_buy_price: number;
  current_price: number;
  invested_value: number;
  current_value: number;
  pnl: number;
  return_pct: number;
}

export type PortfolioRisk = 'Low' | 'Moderate' | 'High';

export interface PortfolioSummary {
  portfolio_id: number;
  portfolio_value: number;
  invested_amount: number;
  total_pnl: number;
  return_pct: number;
  holdings_count: number;
  portfolio_risk: PortfolioRisk;
  health_score: number;
}

export interface PerformancePoint {
  date: string;
  value: number;
  invested: number;
}

export interface PortfolioPerformance {
  points: PerformancePoint[];
  data_source: 'DEV_SAMPLE' | 'LIVE';
}

export interface AllocationSlice {
  label: string;
  value: number;
  pct: number;
}

export interface PortfolioAllocation {
  by_stock: AllocationSlice[];
  by_sector: AllocationSlice[];
}

export interface RiskContribution {
  symbol: string;
  risk_contribution_pct: number;
}

export interface CorrelationEntry {
  symbol_a: string;
  symbol_b: string;
  correlation: number;
}

export interface PortfolioRiskData {
  annualized_volatility: number;
  sharpe_ratio: number;
  max_drawdown: number;
  risk_contributions: RiskContribution[];
  correlation_matrix: CorrelationEntry[];
  sector_concentration: AllocationSlice[];
  top_stock_concentration_pct: number;
  data_source: 'DEV_SAMPLE' | 'LIVE';
}

export interface HealthComponent {
  name: string;
  score: number;
  description: string;
}

export interface PortfolioHealth {
  overall_health: number;
  components: HealthComponent[];
  computed_at: string;
}

export type Severity = 'HIGH' | 'MEDIUM' | 'LOW';

export interface Weakness {
  title: string;
  severity: Severity;
  explanation: string;
  supporting_metric: string;
}

export interface PortfolioWeaknesses {
  weaknesses: Weakness[];
}

export interface StockListItem {
  id: number;
  symbol: string;
  name: string;
  sector: string;
  industry: string;
  exchange: string;
}

export interface StockQuote {
  symbol: string;
  name: string;
  sector: string;
  current_price: number;
  previous_close: number;
  change: number;
  change_percent: number;
  volume: number;
  data_source: 'DEV_SAMPLE' | 'LIVE';
}

export interface StockIndicators {
  sma_20: number;
  sma_50: number;
  ema_20: number;
  rsi_14: number;
  volatility_annualized: number;
  momentum_10d: number;
  daily_return: number;
  cumulative_return_30d: number;
  avg_volume_20d: number;
}

export interface OHLCV {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface StockDetail {
  quote: StockQuote;
  indicators: StockIndicators;
  history: OHLCV[];
}

export interface StockHistory {
  symbol: string;
  data_source: 'DEV_SAMPLE' | 'LIVE';
  points: OHLCV[];
}

export type Direction = 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL';
export type Confidence = 'LOW' | 'MEDIUM' | 'HIGH';

export interface Prediction {
  symbol: string;
  direction: Direction;
  probability: number;
  confidence: Confidence;
  model_name: string;
  prediction_date: string;
  important_features: string[];
  disclaimer: string;
}

export type SentimentLabel = 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL';

export interface NewsItem {
  id: number;
  headline: string;
  source: string;
  url: string | null;
  published_at: string;
  sentiment_label: SentimentLabel;
  sentiment_score: number;
  symbol?: string; // attached client-side when aggregating across holdings
}

export type SentimentTrend = 'IMPROVING' | 'DECLINING' | 'STABLE';

export interface SentimentSummary {
  symbol: string;
  positive_pct: number;
  neutral_pct: number;
  negative_pct: number;
  average_score: number;
  trend: SentimentTrend;
  article_count: number;
  model_used: string;
}

export type DiversificationBenefit = 'High' | 'Moderate' | 'Low';

export interface DiscoverItem {
  symbol: string;
  name: string;
  sector: string;
  current_price: number;
  ml_outlook: Direction;
  prediction_probability: number;
  volatility: number;
  portfolio_fit: number;
  correlation_with_portfolio: number;
  diversification_benefit: DiversificationBenefit;
}

export interface FitFactor {
  name: string;
  contribution: number;
  explanation: string;
}

export interface PortfolioFit {
  symbol: string;
  name: string;
  fit_score: number;
  factors: FitFactor[];
  strengths: string[];
  concerns: string[];
  weights_used: Record<string, number>;
}

export interface ApiError {
  detail: string;
}
