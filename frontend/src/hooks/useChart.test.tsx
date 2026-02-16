import { renderHook, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { createTestQueryClient } from "@/test/helpers";
import { useChart } from "./useChart";
import { mockChartPayload } from "@/test/fixtures";
import type { ReactNode } from "react";

vi.mock("@/lib/api", () => ({
  getChart: vi.fn(),
}));

import { getChart } from "@/lib/api";
const mockGetChart = vi.mocked(getChart);

function createWrapper() {
  const qc = createTestQueryClient();
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  }
  return { Wrapper, qc };
}

describe("useChart", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not fetch when symbol is null", () => {
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useChart(null), { wrapper: Wrapper });
    expect(result.current.isFetching).toBe(false);
    expect(mockGetChart).not.toHaveBeenCalled();
  });

  it("fetches chart data for a symbol", async () => {
    mockGetChart.mockResolvedValue(mockChartPayload);
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useChart("AAPL"), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetChart).toHaveBeenCalledWith("AAPL", 180);
    expect(result.current.data).toEqual(mockChartPayload);
  });

  it("passes custom days parameter", async () => {
    mockGetChart.mockResolvedValue(mockChartPayload);
    const { Wrapper } = createWrapper();
    renderHook(() => useChart("AAPL", 90), { wrapper: Wrapper });

    await waitFor(() => expect(mockGetChart).toHaveBeenCalledWith("AAPL", 90));
  });

  it("uses correct query key including days", async () => {
    mockGetChart.mockResolvedValue(mockChartPayload);
    const { Wrapper, qc } = createWrapper();
    renderHook(() => useChart("AAPL", 30), { wrapper: Wrapper });

    await waitFor(() =>
      expect(qc.getQueryState(["chart", "AAPL", 30])).toBeDefined(),
    );
  });
});
