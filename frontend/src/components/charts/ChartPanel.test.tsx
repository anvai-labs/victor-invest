import { render, screen } from "@testing-library/react";
import { ChartPanel } from "./ChartPanel";
import { mockChartPayload } from "@/test/fixtures";

describe("ChartPanel", () => {
  it("renders price chart card with symbol", () => {
    render(<ChartPanel chart={mockChartPayload} />);
    expect(screen.getByText("Price - AAPL")).toBeInTheDocument();
  });

  it("renders volume/OBV card", () => {
    render(<ChartPanel chart={mockChartPayload} />);
    expect(screen.getByText("Volume / OBV")).toBeInTheDocument();
  });

  it("renders MACD card", () => {
    render(<ChartPanel chart={mockChartPayload} />);
    expect(screen.getByText("MACD")).toBeInTheDocument();
  });

  it("renders RSI card", () => {
    render(<ChartPanel chart={mockChartPayload} />);
    expect(screen.getByText("RSI")).toBeInTheDocument();
  });
});
