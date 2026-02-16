import { render, screen } from "@testing-library/react";
import { PredictionsTab } from "./PredictionsTab";
import { mockPredictionsResponse } from "@/test/fixtures";

describe("PredictionsTab", () => {
  it("shows empty message when no predictions", () => {
    render(<PredictionsTab predictions={undefined} />);
    expect(screen.getByText("No prediction history available.")).toBeInTheDocument();
  });

  it("shows empty message for empty predictions array", () => {
    render(
      <PredictionsTab predictions={{ symbol: "AAPL", predictions: [] }} />,
    );
    expect(screen.getByText("No prediction history available.")).toBeInTheDocument();
  });

  it("renders prediction history table", () => {
    render(<PredictionsTab predictions={mockPredictionsResponse} />);
    expect(screen.getByText("Prediction History")).toBeInTheDocument();
    expect(screen.getByText("2025-01-15")).toBeInTheDocument();
    expect(screen.getByText("2024-12-01")).toBeInTheDocument();
  });

  it("renders tier classification", () => {
    render(<PredictionsTab predictions={mockPredictionsResponse} />);
    expect(screen.getByText("high_conviction")).toBeInTheDocument();
    expect(screen.getByText("moderate")).toBeInTheDocument();
  });

  it("color-codes direction accuracy — correct when direction matches", () => {
    render(<PredictionsTab predictions={mockPredictionsResponse} />);
    // First row: predicted upside 6.85%, actual 30d $190 > $182.50 → correct
    const correctCells = screen.getAllByText("Correct");
    expect(correctCells.length).toBeGreaterThanOrEqual(1);
  });

  it("color-codes direction accuracy — wrong when direction differs", () => {
    render(<PredictionsTab predictions={mockPredictionsResponse} />);
    // Second row: predicted upside 2.86%, actual 30d $170 < $175 → wrong
    const wrongCells = screen.getAllByText("Wrong");
    expect(wrongCells.length).toBeGreaterThanOrEqual(1);
  });

  it("renders per-model fair values section", () => {
    render(<PredictionsTab predictions={mockPredictionsResponse} />);
    expect(screen.getByText("Latest Per-Model Fair Values")).toBeInTheDocument();
  });
});
