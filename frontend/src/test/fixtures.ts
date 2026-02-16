import type {
  AnalysisResponse,
  ChartPayload,
  RankingsResponse,
  SymbolSearchResult,
  UIView,
  UIFundamental,
  UITechnical,
} from "@/lib/types";

export const mockTechnical: UITechnical = {
  trend: "Bullish",
  rsi: 55.3,
  macd_signal: "bullish",
  moving_averages: {
    sma_20: 178.5,
    sma_50: 172.3,
    sma_200: 165.1,
    ema_12: 179.2,
    ema_26: 175.8,
  },
  support_resistance: {
    support: 170.0,
    resistance: 190.0,
  },
  raw_payload: null,
};

export const mockFundamental: UIFundamental = {
  models: [
    {
      name: "DCF",
      fair_value: 195.0,
      weight: 0.4,
      confidence: "high",
      details: {},
    },
    {
      name: "P/E Relative",
      fair_value: 188.0,
      weight: 0.3,
      confidence: "medium",
      details: {},
    },
    {
      name: "GGM",
      fair_value: 201.0,
      weight: 0.3,
      confidence: "low",
      details: {},
    },
  ],
  forward_guidance: {
    revenue_growth_pct: 8.5,
    eps_estimate: 6.75,
    guidance_period: "FY2025",
    source: "Company guidance",
  },
  notes: ["Strong free cash flow generation", "Share buyback program active"],
  raw_payload: null,
};

export const mockView: UIView = {
  symbol: "AAPL",
  company_name: "Apple Inc.",
  sector: "Technology",
  industry: "Consumer Electronics",
  timestamp: "2025-01-15T10:30:00Z",
  summary: {
    action: "Buy",
    composite_score: 72,
    price: 182.5,
    fair_value: 195.0,
    target_return_pct: 6.8,
    valuation_basis: "DCF",
    data_quality: "High",
    thesis: "Strong fundamentals with growing services revenue.",
    key_risks: ["Regulatory pressure", "Supply chain constraints"],
    key_catalysts: ["AI integration", "Services growth"],
  },
  fundamental: mockFundamental,
  technical: mockTechnical,
  signals: [
    { label: "RSI", value: "55.3", sentiment: "neutral" },
    { label: "MACD", value: "Bullish", sentiment: "good" },
    { label: "Trend", value: "Bullish", sentiment: "good" },
  ],
};

export const mockAnalysisResponse: AnalysisResponse = {
  symbol: "AAPL",
  status: "success",
  cached: false,
  timestamp: "2025-01-15T10:30:00Z",
  data: mockView,
};

export const mockChartPayload: ChartPayload = {
  symbol: "AAPL",
  days: 180,
  candles: [
    { date: "2025-01-13", open: 180.0, high: 183.0, low: 179.0, close: 182.0 },
    { date: "2025-01-14", open: 182.0, high: 185.0, low: 181.0, close: 184.0 },
    { date: "2025-01-15", open: 184.0, high: 186.0, low: 182.5, close: 182.5 },
  ],
  volume: [
    { date: "2025-01-13", volume: 50_000_000, obv: 50_000_000 },
    { date: "2025-01-14", volume: 45_000_000, obv: 95_000_000 },
    { date: "2025-01-15", volume: 55_000_000, obv: 40_000_000 },
  ],
  indicators: {
    macd: [
      { date: "2025-01-13", macd: 1.2, signal: 0.8, histogram: 0.4 },
      { date: "2025-01-14", macd: 1.5, signal: 1.0, histogram: 0.5 },
      { date: "2025-01-15", macd: 1.3, signal: 1.1, histogram: 0.2 },
    ],
    rsi: [
      { date: "2025-01-13", rsi: 55.0 },
      { date: "2025-01-14", rsi: 58.0 },
      { date: "2025-01-15", rsi: 55.3 },
    ],
  },
};

export const mockRankingsResponse: RankingsResponse = {
  generated_at: "2025-01-15T10:00:00Z",
  total_symbols: 100,
  longs: [
    {
      rank: 1,
      symbol: "AAPL",
      company_name: "Apple Inc.",
      sector: "Technology",
      composite_score: 82.5,
      action: "Strong Buy",
      target_return_pct: 15.3,
      valuation_basis: "DCF",
    },
    {
      rank: 2,
      symbol: "MSFT",
      company_name: "Microsoft Corp.",
      sector: "Technology",
      composite_score: 78.0,
      action: "Buy",
      target_return_pct: 12.1,
      valuation_basis: "P/E Relative",
    },
    {
      rank: 3,
      symbol: "GOOGL",
      company_name: "Alphabet Inc.",
      sector: "Technology",
      composite_score: 75.0,
      action: "Buy",
      target_return_pct: 10.5,
      valuation_basis: "DCF",
    },
  ],
  shorts: [
    {
      rank: 1,
      symbol: "XYZ",
      company_name: "XYZ Corp.",
      sector: "Consumer Discretionary",
      composite_score: 25.0,
      action: "Sell",
      target_return_pct: -12.0,
      valuation_basis: "P/E Relative",
    },
  ],
  sector_neutral: [
    {
      sector: "Technology",
      longs: [
        {
          rank: 1,
          symbol: "AAPL",
          company_name: "Apple Inc.",
          sector: "Technology",
          composite_score: 82.5,
          action: "Strong Buy",
          target_return_pct: 15.3,
          valuation_basis: "DCF",
        },
      ],
      shorts: [
        {
          rank: 1,
          symbol: "INTC",
          company_name: "Intel Corp.",
          sector: "Technology",
          composite_score: 30.0,
          action: "Sell",
          target_return_pct: -8.0,
          valuation_basis: "DCF",
        },
      ],
    },
  ],
  pairs: [
    {
      long: {
        rank: 1,
        symbol: "AAPL",
        company_name: "Apple Inc.",
        sector: "Technology",
        composite_score: 82.5,
        action: "Strong Buy",
        target_return_pct: 15.3,
        valuation_basis: "DCF",
      },
      short: {
        rank: 1,
        symbol: "INTC",
        company_name: "Intel Corp.",
        sector: "Technology",
        composite_score: 30.0,
        action: "Sell",
        target_return_pct: -8.0,
        valuation_basis: "DCF",
      },
      sector: "Technology",
      spread: 52.5,
    },
  ],
};

export const mockSymbolSearchResults: SymbolSearchResult[] = [
  { symbol: "AAPL", name: "Apple Inc.", sector: "Technology", industry: "Consumer Electronics" },
  { symbol: "AAPLX", name: "Apple Fund", sector: "Finance", industry: "Mutual Funds" },
];
