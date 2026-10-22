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

export interface AnalysisPoint {
  date: string;
  close: number;
  sma_20: number | null;
  ema_20: number | null;
  rsi_14: number | null;
  macd_line: number | null;
  macd_signal: number | null;
  macd_histogram: number | null;
}

export interface ReturnsSummary {
  daily_return: number | null;
  cumulative_return_30d: number | null;
  cumulative_return_90d: number | null;
  cumulative_return_1y: number | null;
}

export interface StockAnalysis {
  symbol: string;
  data_source: 'DEV_SAMPLE' | 'LIVE';
  returns: ReturnsSummary;
  volatility_annualized: number;
  max_drawdown: number;
  beta_vs_nifty50: number | null;
  benchmark_data_source: 'DEV_SAMPLE' | 'LIVE';
  series: AnalysisPoint[];
  disclaimer: string;
}

// --- Phase 14: Risk Attribution ---

export interface RiskAttributionItem {
  symbol: string;
  name: string;
  sector: string;
  weight_pct: number;
  risk_contribution_pct: number;
  marginal_contribution_to_vol: number;
  risk_concentration_ratio: number;
}

export interface PortfolioRiskAttribution {
  portfolio_annualized_volatility: number;
  attributions: RiskAttributionItem[];
  data_source: 'DEV_SAMPLE' | 'LIVE';
}

// --- Phase 9: Portfolio Optimization ---

export type OptimizationMethod = 'min_variance' | 'max_sharpe' | 'risk_parity';

export interface OptimizationAllocation {
  symbol: string;
  current_weight_pct: number;
  suggested_weight_pct: number;
  delta_pct: number;
}

export interface PortfolioOptimization {
  method: OptimizationMethod;
  feasible: boolean;
  note: string | null;
  allocations: OptimizationAllocation[];
  expected_annual_return: number;
  expected_annual_volatility: number;
  expected_sharpe_ratio: number;
  risk_free_rate_assumed: number;
  lookback_days: number;
  data_source: 'DEV_SAMPLE' | 'LIVE';
  disclaimer: string;
}

// --- Phase 11: What-If Simulator ---

export interface WhatIfChange {
  symbol: string;
  new_quantity: number;
}

export interface WhatIfMetrics {
  annualized_volatility: number;
  sharpe_ratio: number;
  var_95: number;
  cvar_95: number;
  var_99: number;
  cvar_99: number;
  diversification_ratio: number;
  hhi_holdings: number;
}

export interface TradeCost {
  brokerage: number;
  stt: number;
  stamp_duty: number;
  exchange_charges: number;
  sebi_fee: number;
  gst: number;
  total: number;
}

export interface WhatIfTrade {
  symbol: string;
  quantity_delta: number;
  trade_value: number;
  action: 'buy' | 'sell';
  estimated_cost: TradeCost | null;
}

export interface WhatIfResult {
  before: WhatIfMetrics;
  after: WhatIfMetrics;
  deltas: Record<string, number>;
  trades: WhatIfTrade[];
  total_estimated_cost: number | null;
  risk_free_rate_assumed: number;
  lookback_days: number;
  data_source: 'DEV_SAMPLE' | 'LIVE';
  disclaimer: string;
}

// --- Phase 16: Fit Engine counterfactuals ---

export type FitPreset = 'balanced' | 'risk_averse' | 'growth_seeking';

export interface FitTermDelta {
  term: string;
  name: string;
  contribution_a: number;
  contribution_b: number;
  delta: number;
}

export interface FitRankingGap {
  symbol_a: string;
  symbol_b: string;
  fit_score_a: number;
  fit_score_b: number;
  logit_gap: number;
  term_deltas: FitTermDelta[];
  preset: string;
  note: string;
}

export interface FitTermScenario {
  term: string;
  name: string;
  current_raw_value: number;
  required_z_delta: number;
  required_raw_delta: number | null;
  target_raw_value: number | null;
}

export interface FitCounterfactual {
  symbol: string;
  fit_score: number;
  target: string;
  already_meets_target: boolean;
  term_scenarios: FitTermScenario[];
  note: string;
}
