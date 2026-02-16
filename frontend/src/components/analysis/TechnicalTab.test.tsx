import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TechnicalTab } from "./TechnicalTab";
import { mockTechnical } from "@/test/fixtures";

describe("TechnicalTab", () => {
  it("renders trend badge", () => {
    render(<TechnicalTab technical={mockTechnical} />);
    expect(screen.getByText("Trend: Bullish")).toBeInTheDocument();
  });

  it("renders RSI badge", () => {
    render(<TechnicalTab technical={mockTechnical} />);
    expect(screen.getByText("RSI: 55.3")).toBeInTheDocument();
  });

  it("renders MACD signal badge", () => {
    render(<TechnicalTab technical={mockTechnical} />);
    expect(screen.getByText("MACD: bullish")).toBeInTheDocument();
  });

  it("renders technical metrics table", () => {
    render(<TechnicalTab technical={mockTechnical} />);
    expect(screen.getByText("Technical Metrics")).toBeInTheDocument();
    expect(screen.getByText("SMA 20")).toBeInTheDocument();
    expect(screen.getByText("Support")).toBeInTheDocument();
    expect(screen.getByText("Resistance")).toBeInTheDocument();
  });

  it("toggles raw payload visibility", async () => {
    const withRaw = { ...mockTechnical, raw_payload: { rsi: 55 } };
    render(<TechnicalTab technical={withRaw} />);

    expect(screen.queryByText(/"rsi"/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByText("Show"));
    expect(screen.getByText(/"rsi"/)).toBeInTheDocument();
  });
});
