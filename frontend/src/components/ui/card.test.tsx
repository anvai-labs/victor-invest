import { render, screen } from "@testing-library/react";
import { Card, CardHeader, CardTitle, CardContent } from "./card";

describe("Card", () => {
  it("renders children", () => {
    render(<Card>Card content</Card>);
    expect(screen.getByText("Card content")).toBeInTheDocument();
  });

  it("applies border and shadow classes", () => {
    render(<Card data-testid="card">Content</Card>);
    const card = screen.getByTestId("card");
    expect(card).toHaveClass("rounded-lg", "border", "shadow-sm");
  });

  it("composes Card with Header, Title, Content", () => {
    render(
      <Card>
        <CardHeader>
          <CardTitle>My Title</CardTitle>
        </CardHeader>
        <CardContent>My Content</CardContent>
      </Card>,
    );
    expect(screen.getByText("My Title")).toBeInTheDocument();
    expect(screen.getByText("My Content")).toBeInTheDocument();
  });

  it("merges custom className on Card", () => {
    render(<Card className="w-full" data-testid="card">Content</Card>);
    expect(screen.getByTestId("card")).toHaveClass("w-full");
  });
});
