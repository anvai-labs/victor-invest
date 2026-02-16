import type {
  AnalysisResponse,
  ChartPayload,
  HealthResponse,
  HistoryEntry,
  RankedSymbol,
  RankingsFilterParams,
  RankingsResponse,
  SymbolSearchResult,
  UIFundamental,
  UISignal,
  UITechnical,
  UIView,
  ValuationModel,
} from "./types";

const BASE = "/ui/api";

async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export function searchSymbols(
  query: string,
  limit = 20,
): Promise<{ query: string; results: SymbolSearchResult[] }> {
  return fetchJSON(`${BASE}/search?query=${encodeURIComponent(query)}&limit=${limit}`);
}

/* eslint-disable @typescript-eslint/no-explicit-any */
function transformModels(raw: any): ValuationModel[] {
  if (!raw) return [];
  // API returns { dcf_professional: {...}, pe: {...} } dict
  if (!Array.isArray(raw)) {
    return Object.entries(raw)
      .filter(([, v]: [string, any]) => v && v.applicable)
      .map(([name, v]: [string, any]) => ({
        name: name.replace(/_/g, " ").replace(/\b\w/g, (c: string) => c.toUpperCase()),
        fair_value: v.fair_value_per_share ?? null,
        weight: v.weight ?? 0,
        confidence: v.confidence_score != null
          ? (v.confidence_score > 1 ? `${v.confidence_score}%` : v.confidence_score >= 0.7 ? "high" : v.confidence_score >= 0.4 ? "medium" : "low")
          : "unknown",
        details: v.assumptions ?? {},
      }));
  }
  return raw;
}

function transformFundamental(raw: any): UIFundamental | null {
  if (!raw) return null;
  const valuation = raw.valuation ?? {};
  return {
    models: transformModels(valuation.models),
    forward_guidance: raw.forward_guidance ?? null,
    notes: raw.notes ?? [],
    raw_payload: raw.sec ?? null,
  };
}

function transformTechnical(raw: any): UITechnical | null {
  if (!raw) return null;
  const levels = raw.levels ?? {};
  return {
    trend: raw.recommendation ?? "neutral",
    rsi: raw.rsi ?? null,
    macd_signal: raw.macd_signal ?? "neutral",
    moving_averages: {
      sma_20: raw.sma_20 ?? null,
      sma_50: raw.sma_50 ?? null,
      sma_200: raw.sma_200 ?? null,
      ema_12: raw.ema_12 ?? null,
      ema_26: raw.ema_26 ?? null,
    },
    support_resistance: {
      support: levels.support_1 ?? levels.support ?? null,
      resistance: levels.resistance_1 ?? levels.resistance ?? null,
    },
    raw_payload: levels.pivot_point ? { pivot_point: levels.pivot_point, ...levels } : null,
  };
}

function buildSignals(summary: any, technical: any): UISignal[] {
  const signals: UISignal[] = [];
  if (technical?.recommendation) {
    const rec = technical.recommendation.toLowerCase();
    signals.push({
      label: "Trend",
      value: technical.recommendation,
      sentiment: rec === "bullish" || rec === "buy" ? "good" : rec === "bearish" || rec === "sell" ? "bad" : "neutral",
    });
  }
  if (technical?.rating != null) {
    signals.push({
      label: "Tech Rating",
      value: String(technical.rating),
      sentiment: technical.rating >= 7 ? "good" : technical.rating <= 3 ? "bad" : "neutral",
    });
  }
  if (summary?.market_regime) {
    const regime = summary.market_regime.toLowerCase();
    signals.push({
      label: "Regime",
      value: summary.market_regime.replace(/_/g, " "),
      sentiment: regime.includes("risk_on") ? "good" : regime.includes("risk_off") ? "bad" : "neutral",
    });
  }
  if (summary?.investment_grade) {
    const grade = summary.investment_grade;
    signals.push({
      label: "Grade",
      value: grade,
      sentiment: grade <= "B" ? "good" : grade >= "D" ? "bad" : "warn",
    });
  }
  return signals;
}

function transformAnalysisResponse(raw: any): AnalysisResponse {
  // If already in frontend shape, return as-is
  if (raw.status && raw.data) return raw as AnalysisResponse;

  const view = raw.view ?? raw.data ?? {};
  const summary = view.summary ?? {};

  const uiView: UIView = {
    symbol: raw.symbol ?? summary.symbol ?? "",
    company_name: summary.company_name ?? raw.symbol ?? "",
    sector: summary.sector ?? "",
    industry: summary.industry ?? "",
    timestamp: raw.cached_at ?? raw.timestamp ?? "",
    summary: {
      action: (summary.action ?? "").replace(/_/g, " "),
      composite_score: summary.confidence_score ?? summary.composite_score ?? 0,
      price: summary.current_price ?? summary.price ?? 0,
      fair_value: summary.blended_fair_value ?? summary.target_price ?? summary.fair_value ?? null,
      target_return_pct: summary.expected_return_pct ?? summary.target_return_pct ?? null,
      valuation_basis: summary.valuation_basis ?? "",
      data_quality: summary.quality_grade ?? summary.data_quality ?? "",
      thesis: summary.thesis ?? "",
      key_risks: summary.key_risks ?? [],
      key_catalysts: summary.key_catalysts ?? [],
    },
    fundamental: transformFundamental(view.fundamental),
    technical: transformTechnical(view.technical),
    signals: view.signals ?? buildSignals(summary, view.technical),
  };

  return {
    symbol: raw.symbol ?? "",
    status: "success",
    cached: raw.source !== "live",
    timestamp: raw.cached_at ?? raw.timestamp ?? "",
    data: uiView,
  };
}
/* eslint-enable @typescript-eslint/no-explicit-any */

export async function getLatestAnalysis(symbol: string): Promise<AnalysisResponse> {
  const raw = await fetchJSON<unknown>(`${BASE}/analysis/${encodeURIComponent(symbol)}/latest`);
  return transformAnalysisResponse(raw);
}

export async function refreshAnalysis(
  symbol: string,
  mode: string = "standard",
): Promise<AnalysisResponse> {
  const raw = await fetchJSON<unknown>(`${BASE}/analysis/${encodeURIComponent(symbol)}/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
  return transformAnalysisResponse(raw);
}

export function getChart(symbol: string, days = 180): Promise<ChartPayload> {
  return fetchJSON(`${BASE}/chart/${encodeURIComponent(symbol)}?days=${days}`);
}

/* eslint-disable @typescript-eslint/no-explicit-any */
function mapRankedSymbol(raw: any, index: number): RankedSymbol {
  return {
    rank: index + 1,
    symbol: raw.symbol ?? "",
    company_name: raw.company_name ?? raw.symbol ?? "",
    sector: raw.sector ?? "",
    composite_score: raw.confidence_score ?? raw.composite_score ?? 0,
    action: (raw.action ?? "").replace(/_/g, " "),
    target_return_pct: raw.expected_return_pct ?? raw.target_return_pct ?? null,
    valuation_basis: raw.valuation_basis ?? "",
  };
}

function transformRankingsResponse(raw: any): RankingsResponse {
  const longs = (raw.overall?.longs ?? raw.longs ?? []).map(mapRankedSymbol);
  const shorts = (raw.overall?.shorts ?? raw.shorts ?? []).map(mapRankedSymbol);
  const sectors = raw.sectors ?? raw.sector_neutral ?? [];
  return {
    generated_at: raw.generated_at ?? "",
    total_symbols: raw.universe?.eligible_symbols ?? raw.total_symbols ?? 0,
    longs,
    shorts,
    sector_neutral: sectors.map((s: any) => ({
      sector: s.sector ?? "",
      longs: (s.longs ?? []).map(mapRankedSymbol),
      shorts: (s.shorts ?? []).map(mapRankedSymbol),
    })),
    pairs: (raw.pairs ?? []).map((p: any) => ({
      long: mapRankedSymbol(p.long, 0),
      short: mapRankedSymbol(p.short, 0),
      sector: p.sector ?? "",
      spread: p.spread_pct ?? p.spread ?? 0,
    })),
  };
}
/* eslint-enable @typescript-eslint/no-explicit-any */

export async function getRankings(params?: RankingsFilterParams): Promise<RankingsResponse> {
  const qs = new URLSearchParams();
  if (params?.top_n != null) qs.set("limit", String(params.top_n));
  if (params?.min_score != null) qs.set("min_quality", String(params.min_score));
  const query = qs.toString();
  const raw = await fetchJSON<unknown>(`${BASE}/rankings${query ? `?${query}` : ""}`);
  return transformRankingsResponse(raw);
}

export function exportRankingsCsvUrl(): string {
  return `${BASE}/rankings/export.csv`;
}

export function getHealth(): Promise<HealthResponse> {
  return fetchJSON(`${BASE}/health`);
}

export function getHistory(symbol: string): Promise<HistoryEntry[]> {
  return fetchJSON(`${BASE}/analysis/${encodeURIComponent(symbol)}/history`);
}
