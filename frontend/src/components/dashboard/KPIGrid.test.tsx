import { render, screen } from "@testing-library/react";
import { KPIGrid } from "./KPIGrid";
import { mockView } from "@/test/fixtures";
import type { UISummary } from "@/lib/types";

describe("KPIGrid", () => {
  it("renders all 6 KPI cards", () => {
    render(<KPIGrid summary={mockView.summary} />);
    expect(screen.getByText("Action")).toBeInTheDocument();
    expect(screen.getByText("Price")).toBeInTheDocument();
    expect(screen.getByText("Fair Value")).toBeInTheDocument();
    expect(screen.getByText("Target Return")).toBeInTheDocument();
    expect(screen.getByText("Basis")).toBeInTheDocument();
    expect(screen.getByText("Quality")).toBeInTheDocument();
  });

  it("displays formatted price", () => {
    render(<KPIGrid summary={mockView.summary} />);
    expect(screen.getByText("$182.50")).toBeInTheDocument();
  });

  it("displays action value", () => {
    render(<KPIGrid summary={mockView.summary} />);
    expect(screen.getByText("Buy")).toBeInTheDocument();
  });

  it("displays valuation basis", () => {
    render(<KPIGrid summary={mockView.summary} />);
    expect(screen.getByText("DCF")).toBeInTheDocument();
  });

  it("handles null fair value with em-dash", () => {
    const summary: UISummary = { ...mockView.summary, fair_value: null };
    render(<KPIGrid summary={summary} />);
    expect(screen.getByText("\u2014")).toBeInTheDocument();
  });
});
