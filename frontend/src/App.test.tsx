import { render, screen } from "@testing-library/react";
import App from "./App";

vi.mock("@/hooks/useAnalysis", () => ({
  useAnalysis: () => ({ data: undefined, isLoading: false, error: null }),
  useRefreshAnalysis: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("@/hooks/useChart", () => ({
  useChart: () => ({ data: undefined }),
}));

vi.mock("@/hooks/useRankings", () => ({
  useRankings: () => ({ data: undefined, isLoading: false, error: null }),
}));

vi.mock("@/lib/api", () => ({
  exportRankingsCsvUrl: () => "/ui/api/rankings/export.csv",
}));

describe("App", () => {
  it("renders the header", () => {
    render(<App />);
    expect(screen.getByText("Victor Research")).toBeInTheDocument();
  });

  it("renders search input", () => {
    render(<App />);
    expect(screen.getByPlaceholderText("Search symbol or company...")).toBeInTheDocument();
  });

  it("shows welcome message when no symbol selected", () => {
    render(<App />);
    expect(screen.getByText("Victor Research Dashboard")).toBeInTheDocument();
    expect(screen.getByText(/Search for a symbol/)).toBeInTheDocument();
  });

  it("renders rankings tab in default view", () => {
    render(<App />);
    expect(screen.getByText("Rankings")).toBeInTheDocument();
  });
});
