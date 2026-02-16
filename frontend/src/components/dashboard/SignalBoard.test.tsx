import { render, screen } from "@testing-library/react";
import { SignalBoard } from "./SignalBoard";
import type { UISignal } from "@/lib/types";

describe("SignalBoard", () => {
  const signals: UISignal[] = [
    { label: "RSI", value: "55.3", sentiment: "neutral" },
    { label: "MACD", value: "Bullish", sentiment: "good" },
    { label: "Trend", value: "Bearish", sentiment: "bad" },
  ];

  it("renders signal badges", () => {
    render(<SignalBoard signals={signals} />);
    expect(screen.getByText("RSI: 55.3")).toBeInTheDocument();
    expect(screen.getByText("MACD: Bullish")).toBeInTheDocument();
    expect(screen.getByText("Trend: Bearish")).toBeInTheDocument();
  });

  it("applies correct variant for sentiment", () => {
    render(<SignalBoard signals={signals} />);
    const good = screen.getByText("MACD: Bullish");
    expect(good).toHaveClass("text-good");
  });

  it("renders nothing for empty signals", () => {
    const { container } = render(<SignalBoard signals={[]} />);
    expect(container.firstChild).toBeNull();
  });
});
