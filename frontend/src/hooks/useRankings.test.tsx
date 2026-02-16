import { renderHook, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { createTestQueryClient } from "@/test/helpers";
import { useRankings } from "./useRankings";
import { mockRankingsResponse } from "@/test/fixtures";
import type { ReactNode } from "react";

vi.mock("@/lib/api", () => ({
  getRankings: vi.fn(),
}));

import { getRankings } from "@/lib/api";
const mockGetRankings = vi.mocked(getRankings);

function createWrapper() {
  const qc = createTestQueryClient();
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  }
  return { Wrapper, qc };
}

describe("useRankings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetches rankings without params", async () => {
    mockGetRankings.mockResolvedValue(mockRankingsResponse);
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useRankings(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetRankings).toHaveBeenCalledWith(undefined);
    expect(result.current.data).toEqual(mockRankingsResponse);
  });

  it("passes filter params through", async () => {
    mockGetRankings.mockResolvedValue(mockRankingsResponse);
    const params = { top_n: 10, min_score: 50 };
    const { Wrapper } = createWrapper();
    renderHook(() => useRankings(params), { wrapper: Wrapper });

    await waitFor(() =>
      expect(mockGetRankings).toHaveBeenCalledWith(params),
    );
  });

  it("uses query key including params", async () => {
    mockGetRankings.mockResolvedValue(mockRankingsResponse);
    const params = { top_n: 5 };
    const { Wrapper, qc } = createWrapper();
    renderHook(() => useRankings(params), { wrapper: Wrapper });

    await waitFor(() =>
      expect(qc.getQueryState(["rankings", params])).toBeDefined(),
    );
  });
});
