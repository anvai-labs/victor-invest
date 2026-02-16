import { renderHook, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { createTestQueryClient } from "@/test/helpers";
import { useSymbolSearch } from "./useSymbolSearch";
import { mockSymbolSearchResults } from "@/test/fixtures";
import type { ReactNode } from "react";

vi.mock("@/lib/api", () => ({
  searchSymbols: vi.fn(),
}));

import { searchSymbols } from "@/lib/api";
const mockSearch = vi.mocked(searchSymbols);

function createWrapper() {
  const qc = createTestQueryClient();
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  }
  return { Wrapper, qc };
}

describe("useSymbolSearch", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not search for empty string", () => {
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useSymbolSearch(""), { wrapper: Wrapper });
    expect(result.current.isFetching).toBe(false);
    expect(mockSearch).not.toHaveBeenCalled();
  });

  it("fetches for non-empty input", async () => {
    mockSearch.mockResolvedValue({ query: "AAPL", results: mockSymbolSearchResults });
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useSymbolSearch("AAPL"), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockSearch).toHaveBeenCalledWith("AAPL");
  });

  it("returns data after successful search", async () => {
    const response = { query: "AAPL", results: mockSymbolSearchResults };
    mockSearch.mockResolvedValue(response);
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useSymbolSearch("AAPL"), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.results).toEqual(mockSymbolSearchResults);
  });

  it("uses correct query key", async () => {
    mockSearch.mockResolvedValue({ query: "MSFT", results: [] });
    const { Wrapper, qc } = createWrapper();
    renderHook(() => useSymbolSearch("MSFT"), { wrapper: Wrapper });

    await waitFor(() =>
      expect(qc.getQueryState(["symbol-search", "MSFT"])).toBeDefined(),
    );
  });

  it("enables query for single-char input", async () => {
    mockSearch.mockResolvedValue({ query: "A", results: [] });
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useSymbolSearch("A"), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockSearch).toHaveBeenCalledWith("A");
  });
});
