import type {
  AnalysisResponse,
  ChartPayload,
  HealthResponse,
  HistoryEntry,
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

export function getRankings(params?: RankingsFilterParams): Promise<RankingsResponse> {
  const qs = new URLSearchParams();
  if (params?.min_score != null) qs.set("min_score", String(params.min_score));
  if (params?.max_score != null) qs.set("max_score", String(params.max_score));
  if (params?.top_n != null) qs.set("top_n", String(params.top_n));
  if (params?.sectors?.length) qs.set("sectors", params.sectors.join(","));
  const query = qs.toString();
  return fetchJSON(`${BASE}/rankings${query ? `?${query}` : ""}`);
}

export function exportRankingsCsvUrl(): string {
  return `${BASE}/rankings/export?format=csv`;
}

export function getHealth(): Promise<HealthResponse> {
  return fetchJSON(`${BASE}/health`);
}

export function getHistory(symbol: string): Promise<HistoryEntry[]> {
  return fetchJSON(`${BASE}/analysis/${encodeURIComponent(symbol)}/history`);
}
