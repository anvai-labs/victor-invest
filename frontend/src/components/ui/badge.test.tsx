import { render, screen } from "@testing-library/react";
import { Badge } from "./badge";

describe("Badge", () => {
  it("renders text content", () => {
    render(<Badge>Status</Badge>);
    expect(screen.getByText("Status")).toBeInTheDocument();
  });

  it("applies default variant", () => {
    render(<Badge>Default</Badge>);
    expect(screen.getByText("Default")).toHaveClass("bg-slate-100");
  });

  it("applies good variant", () => {
    render(<Badge variant="good">Good</Badge>);
    expect(screen.getByText("Good")).toHaveClass("text-good");
  });

  it("applies bad variant", () => {
    render(<Badge variant="bad">Bad</Badge>);
    expect(screen.getByText("Bad")).toHaveClass("text-bad");
  });

  it("applies warn variant", () => {
    render(<Badge variant="warn">Warn</Badge>);
    expect(screen.getByText("Warn")).toHaveClass("text-warn");
  });

  it("merges custom className", () => {
    render(<Badge className="ml-2">Custom</Badge>);
    expect(screen.getByText("Custom")).toHaveClass("ml-2");
  });
});
