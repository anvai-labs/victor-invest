import {
  searchSymbols,
  getLatestAnalysis,
  refreshAnalysis,
  getChart,
  getRankings,
  exportRankingsCsvUrl,
  getHealth,
  getHistory,
} from "./api";

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

function jsonResponse(data: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : "Error",
    json: () => Promise.resolve(data),
    text: () => Promise.resolve(JSON.stringify(data)),
  };
}

beforeEach(() => {
  mockFetch.mockReset();
});

describe("fetchJSON (via API functions)", () => {
  it("throws on non-ok response", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ error: "not found" }, 404));
    await expect(getHealth()).rejects.toThrow("404");
  });

  it("includes response body in error message", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      text: () => Promise.resolve("server broke"),
    });
    await expect(getHealth()).rejects.toThrow("server broke");
  });
});

describe("searchSymbols", () => {
  it("calls correct URL with encoded query", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ query: "AA", results: [] }));
    await searchSymbols("AA");
    expect(mockFetch).toHaveBeenCalledWith(
      "/ui/api/search?query=AA&limit=20",
      undefined,
    );
  });

  it("passes custom limit", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ query: "AA", results: [] }));
    await searchSymbols("AA", 5);
    expect(mockFetch).toHaveBeenCalledWith(
      "/ui/api/search?query=AA&limit=5",
      undefined,
    );
  });
});

describe("getLatestAnalysis", () => {
  it("calls correct URL", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ symbol: "AAPL" }));
    await getLatestAnalysis("AAPL");
    expect(mockFetch).toHaveBeenCalledWith(
      "/ui/api/analysis/AAPL/latest",
      undefined,
    );
  });
});

describe("refreshAnalysis", () => {
  it("sends POST with mode and valuation_basis", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ symbol: "AAPL" }));
    await refreshAnalysis("AAPL", { mode: "quick", valuation_basis: "ttm" });
    const call = mockFetch.mock.calls[0]!;
    const body = JSON.parse(call[1].body as string);
    expect(body.mode).toBe("quick");
    expect(body.valuation_basis).toBe("ttm");
    expect(body.force_refresh).toBe(true);
  });

  it("defaults to comprehensive mode with ttm basis", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ symbol: "AAPL" }));
    await refreshAnalysis("AAPL");
    const call = mockFetch.mock.calls[0]!;
    const body = JSON.parse(call[1].body as string);
    expect(body.mode).toBe("comprehensive");
    expect(body.valuation_basis).toBe("ttm");
  });

  it("includes forward_horizon when basis is forward", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ symbol: "AAPL" }));
    await refreshAnalysis("AAPL", { valuation_basis: "forward", forward_horizon: "2q" });
    const call = mockFetch.mock.calls[0]!;
    const body = JSON.parse(call[1].body as string);
    expect(body.valuation_basis).toBe("forward");
    expect(body.forward_horizon).toBe("2q");
  });

  it("omits forward_horizon when basis is ttm", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ symbol: "AAPL" }));
    await refreshAnalysis("AAPL", { valuation_basis: "ttm", forward_horizon: "1y" });
    const call = mockFetch.mock.calls[0]!;
    const body = JSON.parse(call[1].body as string);
    expect(body.forward_horizon).toBeUndefined();
  });
});

describe("getChart", () => {
  it("calls correct URL with days", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ candles: [], volume: [], indicators: { macd: [], rsi: [] }, symbol: "AAPL", days: 90 }));
    await getChart("AAPL", 90);
    expect(mockFetch).toHaveBeenCalledWith(
      "/ui/api/chart/AAPL?days=90",
      undefined,
    );
  });

  it("defaults to 180 days", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ candles: [], volume: [], indicators: { macd: [], rsi: [] }, symbol: "AAPL", days: 180 }));
    await getChart("AAPL");
    expect(mockFetch).toHaveBeenCalledWith(
      "/ui/api/chart/AAPL?days=180",
      undefined,
    );
  });

  it("transforms columnar API response to row format", async () => {
    mockFetch.mockResolvedValue(jsonResponse({
      symbol: "AAPL",
      chart: {
        symbol: "AAPL",
        days: 3,
        dates: ["2025-01-13", "2025-01-14", "2025-01-15"],
        ohlcv: {
          open: [180, 182, 184],
          high: [183, 185, 186],
          low: [179, 181, 182.5],
          close: [182, 184, 182.5],
          volume: [50000000, 45000000, 55000000],
        },
        indicators: {
          macd: [1.2, 1.5, 1.3],
          macd_signal: [0.8, 1.0, 1.1],
          macd_hist: [0.4, 0.5, 0.2],
          rsi_14: [55, 58, 55.3],
          obv: [50000000, 95000000, 40000000],
          sma_20: [178.5, 179.0, 179.5],
          sma_50: [null, null, 172.8],
          bb_upper: [190, 191, 191.5],
          bb_middle: [178.5, 179, 179.5],
          bb_lower: [167, 167, 167.5],
        },
      },
    }));
    const result = await getChart("AAPL");
    expect(result.candles).toHaveLength(3);
    expect(result.candles[0]).toEqual({ date: "2025-01-13", open: 180, high: 183, low: 179, close: 182 });
    expect(result.volume).toHaveLength(3);
    expect(result.volume[0]).toEqual({ date: "2025-01-13", volume: 50000000, obv: 50000000 });
    expect(result.indicators.macd).toHaveLength(3);
    expect(result.indicators.macd[0]).toEqual({ date: "2025-01-13", macd: 1.2, signal: 0.8, histogram: 0.4 });
    expect(result.indicators.rsi).toHaveLength(3);
    expect(result.indicators.rsi[0]).toEqual({ date: "2025-01-13", rsi: 55 });
    // Overlays
    expect(result.overlays).toHaveLength(3);
    expect(result.overlays[0]!.sma_20).toBe(178.5);
    expect(result.overlays[0]!.bb_upper).toBe(190);
    expect(result.overlays[1]!.sma_50).toBeNull();
    expect(result.overlays[2]!.sma_50).toBe(172.8);
  });

  it("passes through already-transformed chart data", async () => {
    const rowData = {
      symbol: "AAPL", days: 1,
      candles: [{ date: "2025-01-13", open: 180, high: 183, low: 179, close: 182 }],
      volume: [{ date: "2025-01-13", volume: 50000000, obv: 50000000 }],
      indicators: { macd: [], rsi: [] },
      overlays: [],
    };
    mockFetch.mockResolvedValue(jsonResponse(rowData));
    const result = await getChart("AAPL");
    expect(result.candles).toHaveLength(1);
    expect(result.candles[0]!.open).toBe(180);
  });
});

describe("getRankings", () => {
  it("calls without params", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ overall: { longs: [], shorts: [] } }));
    await getRankings();
    expect(mockFetch).toHaveBeenCalledWith("/ui/api/rankings", undefined);
  });

  it("maps top_n to limit param", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ overall: { longs: [], shorts: [] } }));
    await getRankings({ top_n: 10, min_score: 50 });
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("limit=10");
    expect(url).toContain("min_quality=50");
  });

  it("transforms API response to frontend shape", async () => {
    mockFetch.mockResolvedValue(jsonResponse({
      generated_at: "2025-01-01",
      universe: { eligible_symbols: 100 },
      overall: {
        longs: [{ symbol: "AAPL", sector: "tech", action: "strong_buy", confidence_score: 80, expected_return_pct: 15 }],
        shorts: [],
      },
      sectors: [],
      pairs: [],
    }));
    const result = await getRankings();
    expect(result.total_symbols).toBe(100);
    expect(result.longs[0]!.symbol).toBe("AAPL");
    expect(result.longs[0]!.composite_score).toBe(80);
    expect(result.longs[0]!.action).toBe("strong buy");
    expect(result.longs[0]!.target_return_pct).toBe(15);
  });
});

describe("exportRankingsCsvUrl", () => {
  it("returns correct URL", () => {
    expect(exportRankingsCsvUrl()).toBe("/ui/api/rankings/export.csv");
  });
});

describe("getHealth", () => {
  it("calls correct URL", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ status: "ok" }));
    await getHealth();
    expect(mockFetch).toHaveBeenCalledWith("/ui/api/health", undefined);
  });
});

describe("getHistory", () => {
  it("calls correct URL", async () => {
    mockFetch.mockResolvedValue(jsonResponse([]));
    await getHistory("AAPL");
    expect(mockFetch).toHaveBeenCalledWith(
      "/ui/api/analysis/AAPL/history",
      undefined,
    );
  });
});
