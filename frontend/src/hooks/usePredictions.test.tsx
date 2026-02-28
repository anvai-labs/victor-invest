import { renderHook, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { createTestQueryClient } from "@/test/helpers";
import { usePredictions } from "./usePredictions";
import { mockPredictionsResponse } from "@/test/fixtures";
import type { ReactNode } from "react";

vi.mock("@/lib/api", () => ({
  getPredictions: vi.fn(),
}));

import { getPredictions } from "@/lib/api";
const mockGetPredictions = vi.mocked(getPredictions);

function createWrapper() {
  const qc = createTestQueryClient();
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  }
  return { Wrapper, qc };
}

describe("usePredictions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not fetch when symbol is null", () => {
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => usePredictions(null), { wrapper: Wrapper });
    expect(result.current.isFetching).toBe(false);
    expect(mockGetPredictions).not.toHaveBeenCalled();
  });

  it("fetches when symbol is provided", async () => {
    mockGetPredictions.mockResolvedValue(mockPredictionsResponse);
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => usePredictions("AAPL"), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetPredictions).toHaveBeenCalledWith("AAPL");
    expect(result.current.data).toEqual(mockPredictionsResponse);
  });

  it("uses correct query key", async () => {
    mockGetPredictions.mockResolvedValue(mockPredictionsResponse);
    const { Wrapper, qc } = createWrapper();
    renderHook(() => usePredictions("MSFT"), { wrapper: Wrapper });

    await waitFor(() =>
      expect(qc.getQueryState(["predictions", "MSFT"])).toBeDefined(),
    );
  });
});
