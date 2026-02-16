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
  it("sends POST with mode", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ symbol: "AAPL" }));
    await refreshAnalysis("AAPL", "quick");
    expect(mockFetch).toHaveBeenCalledWith(
      "/ui/api/analysis/AAPL/refresh",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ mode: "quick" }),
      }),
    );
  });

  it("defaults to standard mode", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ symbol: "AAPL" }));
    await refreshAnalysis("AAPL");
    const call = mockFetch.mock.calls[0]!;
    expect(JSON.parse(call[1].body as string)).toEqual({ mode: "standard" });
  });
});

describe("getChart", () => {
  it("calls correct URL with days", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ symbol: "AAPL" }));
    await getChart("AAPL", 90);
    expect(mockFetch).toHaveBeenCalledWith(
      "/ui/api/chart/AAPL?days=90",
      undefined,
    );
  });

  it("defaults to 180 days", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ symbol: "AAPL" }));
    await getChart("AAPL");
    expect(mockFetch).toHaveBeenCalledWith(
      "/ui/api/chart/AAPL?days=180",
      undefined,
    );
  });
});

describe("getRankings", () => {
  it("calls without params", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ longs: [] }));
    await getRankings();
    expect(mockFetch).toHaveBeenCalledWith("/ui/api/rankings", undefined);
  });

  it("includes filter params", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ longs: [] }));
    await getRankings({ min_score: 50, top_n: 10, sectors: ["Technology", "Health Care"] });
    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("min_score=50");
    expect(url).toContain("top_n=10");
    expect(url).toContain("sectors=Technology%2CHealth+Care");
  });
});

describe("exportRankingsCsvUrl", () => {
  it("returns correct URL", () => {
    expect(exportRankingsCsvUrl()).toBe("/ui/api/rankings/export?format=csv");
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
