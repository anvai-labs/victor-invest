import type {
  AnalysisResponse,
  ChartPayload,
  HealthResponse,
  HistoryEntry,
  RankedSymbol,
  RankingsFilterParams,
  RankingsResponse,
  SymbolSearchResult,
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

export function getLatestAnalysis(symbol: string): Promise<AnalysisResponse> {
  return fetchJSON(`${BASE}/analysis/${encodeURIComponent(symbol)}/latest`);
}

export function refreshAnalysis(
  symbol: string,
  mode: string = "standard",
): Promise<AnalysisResponse> {
  return fetchJSON(`${BASE}/analysis/${encodeURIComponent(symbol)}/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
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
