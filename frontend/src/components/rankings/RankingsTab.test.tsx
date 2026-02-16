import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@/test/helpers";
import { mockRankingsResponse } from "@/test/fixtures";
import { RankingsTab } from "./RankingsTab";

vi.mock("@/hooks/useRankings", () => ({
  useRankings: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  exportRankingsCsvUrl: () => "/ui/api/rankings/export.csv",
}));

import { useRankings } from "@/hooks/useRankings";
const mockUseRankings = vi.mocked(useRankings);

describe("RankingsTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading state", () => {
    mockUseRankings.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as ReturnType<typeof useRankings>);

    renderWithProviders(<RankingsTab />);
    expect(screen.getByText("Loading rankings...")).toBeInTheDocument();
  });

  it("shows error state", () => {
    mockUseRankings.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("Network error"),
    } as ReturnType<typeof useRankings>);

    renderWithProviders(<RankingsTab />);
    expect(screen.getByText(/Failed to load rankings/)).toBeInTheDocument();
  });

  it("renders longs and shorts tables", async () => {
    mockUseRankings.mockReturnValue({
      data: mockRankingsResponse,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useRankings>);

    renderWithProviders(<RankingsTab />);
    await waitFor(() => {
      expect(screen.getByText("Longs")).toBeInTheDocument();
      expect(screen.getByText("Shorts")).toBeInTheDocument();
    });

    // AAPL appears in longs, sector-neutral, and pairs
    expect(screen.getAllByText("AAPL").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("XYZ")).toBeInTheDocument();
  });

  it("renders CSV export link", () => {
    mockUseRankings.mockReturnValue({
      data: mockRankingsResponse,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useRankings>);

    renderWithProviders(<RankingsTab />);
    const link = screen.getByText("CSV").closest("a");
    expect(link).toHaveAttribute("href", "/ui/api/rankings/export.csv");
  });

  it("renders total symbols count", () => {
    mockUseRankings.mockReturnValue({
      data: mockRankingsResponse,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useRankings>);

    renderWithProviders(<RankingsTab />);
    expect(screen.getByText("100 symbols ranked")).toBeInTheDocument();
  });

  it("renders pair trades section", () => {
    mockUseRankings.mockReturnValue({
      data: mockRankingsResponse,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useRankings>);

    renderWithProviders(<RankingsTab />);
    expect(screen.getByText("Pair Trades")).toBeInTheDocument();
  });
});
