import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Input } from "./input";

describe("Input", () => {
  it("renders an input element", () => {
    render(<Input placeholder="Type here" />);
    expect(screen.getByPlaceholderText("Type here")).toBeInTheDocument();
  });

  it("accepts and displays value", async () => {
    render(<Input data-testid="inp" />);
    const input = screen.getByTestId("inp");
    await userEvent.type(input, "hello");
    expect(input).toHaveValue("hello");
  });

  it("merges custom className", () => {
    render(<Input className="w-64" data-testid="inp" />);
    expect(screen.getByTestId("inp")).toHaveClass("w-64");
  });

  it("supports disabled state", () => {
    render(<Input disabled data-testid="inp" />);
    expect(screen.getByTestId("inp")).toBeDisabled();
  });
});
