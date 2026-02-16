/* Victor-Invest API type definitions.
   Mirrors Pydantic models from victor_invest/api/app.py. */

export interface AnalysisRequest {
  mode?: "quick" | "standard" | "comprehensive";
  force_refresh?: boolean;
}

export interface AnalysisResponse {
  symbol: string;
  status: "success" | "error";
  cached: boolean;
  timestamp: string;
  data: UIView | null;
  error?: string;
}

export interface UIRefreshRequest {
  mode?: "quick" | "standard" | "comprehensive";
  valuation_basis?: "ttm" | "forward";
  forward_horizon?: "1q" | "2q" | "3q" | "1y";
  force_refresh?: boolean;
}

export interface UIView {
  symbol: string;
  company_name: string;
  sector: string;
  industry: string;
  timestamp: string;
  summary: UISummary;
  fundamental: UIFundamental | null;
  technical: UITechnical | null;
  signals: UISignal[];
}

export interface UISummary {
  action: string;
  composite_score: number;
  price: number;
  fair_value: number | null;
  target_return_pct: number | null;
  valuation_basis: string;
  data_quality: string;
  thesis: string;
  key_risks: string[];
  key_catalysts: string[];
}

export interface UIFundamental {
  models: ValuationModel[];
  forward_guidance: ForwardGuidance | null;
  notes: string[];
  raw_payload: Record<string, unknown> | null;
}

export interface ValuationModel {
  name: string;
  fair_value: number | null;
  weight: number;
  confidence: string;
  details: Record<string, unknown>;
}

export interface ForwardGuidance {
  revenue_growth_pct: number | null;
  eps_estimate: number | null;
  guidance_period: string;
  source: string;
  revenue_low: number | null;
  revenue_high: number | null;
  revenue_mid: number | null;
  filing_date: string | null;
}

export interface UITechnical {
  trend: string;
  rsi: number | null;
  macd_signal: string;
  moving_averages: MovingAverages;
  support_resistance: SupportResistance;
  raw_payload: Record<string, unknown> | null;
}

export interface MovingAverages {
  sma_20: number | null;
  sma_50: number | null;
  sma_200: number | null;
  ema_12: number | null;
  ema_26: number | null;
}

export interface SupportResistance {
  support: number | null;
  resistance: number | null;
  support_2: number | null;
  resistance_2: number | null;
  pivot_point: number | null;
}

export interface UISignal {
  label: string;
  value: string;
  sentiment: "good" | "bad" | "warn" | "neutral";
}

export interface ChartPayload {
  symbol: string;
  days: number;
  candles: Candle[];
  volume: VolumeBar[];
  indicators: ChartIndicators;
  overlays: PriceOverlay[];
}

export interface Candle {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface PriceOverlay {
  date: string;
  sma_20: number | null;
  sma_50: number | null;
  sma_200: number | null;
  ema_20: number | null;
  ema_50: number | null;
  bb_upper: number | null;
  bb_middle: number | null;
  bb_lower: number | null;
}

export interface VolumeBar {
  date: string;
  volume: number;
  obv: number;
}

export interface ChartIndicators {
  macd: MacdPoint[];
  rsi: RsiPoint[];
}

export interface MacdPoint {
  date: string;
  macd: number;
  signal: number;
  histogram: number;
}

export interface RsiPoint {
  date: string;
  rsi: number;
}

export interface SymbolSearchResult {
  symbol: string;
  name: string;
  sector: string;
  industry: string;
}

export interface RankingsResponse {
  generated_at: string;
  total_symbols: number;
  longs: RankedSymbol[];
  shorts: RankedSymbol[];
  sector_neutral: SectorGroup[];
  pairs: PairTrade[];
}

export interface RankedSymbol {
  rank: number;
  symbol: string;
  company_name: string;
  sector: string;
  composite_score: number;
  action: string;
  target_return_pct: number | null;
  valuation_basis: string;
}

export interface SectorGroup {
  sector: string;
  longs: RankedSymbol[];
  shorts: RankedSymbol[];
}

export interface PairTrade {
  long: RankedSymbol;
  short: RankedSymbol;
  sector: string;
  spread: number;
}

export interface PortfolioLeg {
  symbol: string;
  side: "long" | "short";
  weight: number;
  sector: string;
  score: number;
}

export interface HealthResponse {
  status: string;
  version: string;
  database: string;
  cache: string;
  llm: string;
}

export interface HistoryEntry {
  symbol: string;
  timestamp: string;
  action: string;
  composite_score: number;
  price: number;
}

export interface RankingsFilterParams {
  min_score?: number;
  max_score?: number;
  sectors?: string[];
  top_n?: number;
}

export interface PredictionRecord {
  id: number;
  symbol: string;
  analysis_date: string;
  blended_fair_value: number | null;
  current_price: number | null;
  predicted_upside_pct: number | null;
  model_fair_values: Record<string, number | null>;
  actual_price_30d: number | null;
  actual_price_90d: number | null;
  actual_price_365d: number | null;
  reward_30d: number | null;
  reward_90d: number | null;
  tier_classification: string;
}

export interface PredictionsResponse {
  symbol: string;
  predictions: PredictionRecord[];
}
