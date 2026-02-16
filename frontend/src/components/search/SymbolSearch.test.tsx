import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";
import { createTestQueryClient } from "@/test/helpers";
import { mockSymbolSearchResults } from "@/test/fixtures";
import { SymbolSearch } from "./SymbolSearch";
import type { ReactNode } from "react";

vi.mock("@/hooks/useSymbolSearch", () => ({
  useSymbolSearch: vi.fn(),
}));

import { useSymbolSearch } from "@/hooks/useSymbolSearch";
const mockUseSymbolSearch = vi.mocked(useSymbolSearch);

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={createTestQueryClient()}>
      {children}
    </QueryClientProvider>
  );
}

describe("SymbolSearch", () => {
  const onSelect = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseSymbolSearch.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useSymbolSearch>);
  });

  it("renders search input", () => {
    render(<SymbolSearch onSelect={onSelect} />, { wrapper: Wrapper });
    expect(screen.getByPlaceholderText("Search symbol or company...")).toBeInTheDocument();
  });

  it("shows results dropdown when data available and input focused", async () => {
    mockUseSymbolSearch.mockReturnValue({
      data: { query: "AAPL", results: mockSymbolSearchResults },
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useSymbolSearch>);

    render(<SymbolSearch onSelect={onSelect} />, { wrapper: Wrapper });
    const input = screen.getByPlaceholderText("Search symbol or company...");

    await userEvent.type(input, "AAPL");

    await waitFor(() => {
      expect(screen.getByText("Apple Inc.")).toBeInTheDocument();
    });
  });

  it("calls onSelect when a result is clicked", async () => {
    mockUseSymbolSearch.mockReturnValue({
      data: { query: "AAPL", results: mockSymbolSearchResults },
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useSymbolSearch>);

    render(<SymbolSearch onSelect={onSelect} />, { wrapper: Wrapper });
    const input = screen.getByPlaceholderText("Search symbol or company...");
    await userEvent.type(input, "AAPL");

    await waitFor(() => {
      expect(screen.getByText("Apple Inc.")).toBeInTheDocument();
    });

    // Click on the first result
    const buttons = screen.getAllByRole("button");
    const resultBtn = buttons.find((b) => b.textContent?.includes("Apple Inc."));
    expect(resultBtn).toBeDefined();
    await userEvent.click(resultBtn!);

    expect(onSelect).toHaveBeenCalledWith("AAPL");
  });

  it("does not show dropdown when no results", () => {
    mockUseSymbolSearch.mockReturnValue({
      data: { query: "ZZZ", results: [] },
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useSymbolSearch>);

    render(<SymbolSearch onSelect={onSelect} />, { wrapper: Wrapper });
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
  });
});
