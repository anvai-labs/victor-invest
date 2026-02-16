import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Header } from "./Header";

describe("Header", () => {
  it("renders the title", () => {
    render(<Header />);
    expect(screen.getByText("Victor Research")).toBeInTheDocument();
  });

  it("renders dark mode toggle button", () => {
    render(<Header />);
    expect(screen.getByRole("button", { name: "Toggle dark mode" })).toBeInTheDocument();
  });

  it("toggles dark class on document when clicked", async () => {
    render(<Header />);
    const btn = screen.getByRole("button", { name: "Toggle dark mode" });

    // Click to toggle dark mode
    await userEvent.click(btn);
    expect(document.documentElement.classList.contains("dark")).toBe(true);

    // Click again to toggle back
    await userEvent.click(btn);
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });
});
