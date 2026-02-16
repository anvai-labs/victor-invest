import { renderHook, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { createTestQueryClient } from "@/test/helpers";
import { useAnalysis, useRefreshAnalysis } from "./useAnalysis";
import { mockAnalysisResponse } from "@/test/fixtures";
import type { ReactNode } from "react";

vi.mock("@/lib/api", () => ({
  getLatestAnalysis: vi.fn(),
  refreshAnalysis: vi.fn(),
}));

import { getLatestAnalysis, refreshAnalysis } from "@/lib/api";
const mockGetLatest = vi.mocked(getLatestAnalysis);
const mockRefresh = vi.mocked(refreshAnalysis);

function createWrapper() {
  const qc = createTestQueryClient();
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  }
  return { Wrapper, qc };
}

describe("useAnalysis", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not fetch when symbol is null", () => {
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useAnalysis(null), { wrapper: Wrapper });
    expect(result.current.isFetching).toBe(false);
    expect(mockGetLatest).not.toHaveBeenCalled();
  });

  it("fetches when symbol is provided", async () => {
    mockGetLatest.mockResolvedValue(mockAnalysisResponse);
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useAnalysis("AAPL"), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetLatest).toHaveBeenCalledWith("AAPL");
    expect(result.current.data).toEqual(mockAnalysisResponse);
  });

  it("uses correct query key", async () => {
    mockGetLatest.mockResolvedValue(mockAnalysisResponse);
    const { Wrapper, qc } = createWrapper();
    renderHook(() => useAnalysis("MSFT"), { wrapper: Wrapper });

    await waitFor(() =>
      expect(qc.getQueryState(["analysis", "MSFT"])).toBeDefined(),
    );
  });
});

describe("useRefreshAnalysis", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls refreshAnalysis with symbol and mode", async () => {
    mockRefresh.mockResolvedValue(mockAnalysisResponse);
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useRefreshAnalysis("AAPL"), {
      wrapper: Wrapper,
    });

    result.current.mutate("quick");
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockRefresh).toHaveBeenCalledWith("AAPL", "quick");
  });

  it("invalidates analysis query on success", async () => {
    mockRefresh.mockResolvedValue(mockAnalysisResponse);
    const { Wrapper, qc } = createWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => useRefreshAnalysis("AAPL"), {
      wrapper: Wrapper,
    });

    result.current.mutate("standard");
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["analysis", "AAPL"],
    });
  });
});
