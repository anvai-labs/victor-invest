import { render, screen } from "@testing-library/react";
import { SummaryTab } from "./SummaryTab";
import { mockView } from "@/test/fixtures";

describe("SummaryTab", () => {
  it("renders KPI grid section", () => {
    render(<SummaryTab view={mockView} />);
    expect(screen.getByText("Action")).toBeInTheDocument();
    expect(screen.getByText("Price")).toBeInTheDocument();
  });

  it("renders investment thesis", () => {
    render(<SummaryTab view={mockView} />);
    expect(screen.getByText("Investment Thesis")).toBeInTheDocument();
    expect(screen.getByText(mockView.summary.thesis)).toBeInTheDocument();
  });

  it("renders catalysts and risks", () => {
    render(<SummaryTab view={mockView} />);
    expect(screen.getByText("Catalysts")).toBeInTheDocument();
    expect(screen.getByText("AI integration")).toBeInTheDocument();
    expect(screen.getByText("Risks")).toBeInTheDocument();
    expect(screen.getByText("Regulatory pressure")).toBeInTheDocument();
  });

  it("renders signals section", () => {
    render(<SummaryTab view={mockView} />);
    expect(screen.getByText("Signals")).toBeInTheDocument();
    expect(screen.getByText("RSI: 55.3")).toBeInTheDocument();
  });

  it("renders fair value range table when models have fair values", () => {
    render(<SummaryTab view={mockView} />);
    expect(screen.getByText("Fair Value Range")).toBeInTheDocument();
    // DCF appears in both KPIGrid (Basis) and the fair value table
    expect(screen.getAllByText("DCF").length).toBeGreaterThanOrEqual(2);
  });
});
