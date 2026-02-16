import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FundamentalTab } from "./FundamentalTab";
import { mockFundamental } from "@/test/fixtures";

describe("FundamentalTab", () => {
  it("renders valuation models table", () => {
    render(<FundamentalTab fundamental={mockFundamental} />);
    expect(screen.getByText("Valuation Models")).toBeInTheDocument();
    expect(screen.getByText("DCF")).toBeInTheDocument();
    expect(screen.getByText("P/E Relative")).toBeInTheDocument();
    expect(screen.getByText("GGM")).toBeInTheDocument();
  });

  it("renders forward guidance section", () => {
    render(<FundamentalTab fundamental={mockFundamental} />);
    expect(screen.getByText("Forward Guidance")).toBeInTheDocument();
    expect(screen.getByText("FY2025")).toBeInTheDocument();
    expect(screen.getByText("8.5%")).toBeInTheDocument();
  });

  it("renders notes", () => {
    render(<FundamentalTab fundamental={mockFundamental} />);
    expect(screen.getByText("Notes")).toBeInTheDocument();
    expect(screen.getByText("Strong free cash flow generation")).toBeInTheDocument();
  });

  it("toggles raw payload visibility", async () => {
    const withRaw = { ...mockFundamental, raw_payload: { key: "value" } };
    render(<FundamentalTab fundamental={withRaw} />);

    expect(screen.getByText("Raw Payload")).toBeInTheDocument();
    expect(screen.queryByText(/"key"/)).not.toBeInTheDocument();

    await userEvent.click(screen.getByText("Show"));
    expect(screen.getByText(/"key"/)).toBeInTheDocument();

    await userEvent.click(screen.getByText("Hide"));
    expect(screen.queryByText(/"key"/)).not.toBeInTheDocument();
  });
});
