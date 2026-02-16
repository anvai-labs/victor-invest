import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Select } from "./select";

describe("Select", () => {
  it("renders with options", () => {
    render(
      <Select data-testid="sel">
        <option value="a">Alpha</option>
        <option value="b">Beta</option>
      </Select>,
    );
    expect(screen.getByTestId("sel")).toBeInTheDocument();
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();
  });

  it("fires onChange when value changes", async () => {
    const onChange = vi.fn();
    render(
      <Select data-testid="sel" onChange={onChange}>
        <option value="a">Alpha</option>
        <option value="b">Beta</option>
      </Select>,
    );
    await userEvent.selectOptions(screen.getByTestId("sel"), "b");
    expect(onChange).toHaveBeenCalled();
  });

  it("merges custom className", () => {
    render(
      <Select className="w-48" data-testid="sel">
        <option>X</option>
      </Select>,
    );
    expect(screen.getByTestId("sel")).toHaveClass("w-48");
  });
});
