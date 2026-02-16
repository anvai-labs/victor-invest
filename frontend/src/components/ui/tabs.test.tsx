import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "./tabs";

describe("Tabs", () => {
  function renderTabs() {
    return render(
      <Tabs defaultValue="one">
        <TabsList>
          <TabsTrigger value="one">Tab One</TabsTrigger>
          <TabsTrigger value="two">Tab Two</TabsTrigger>
        </TabsList>
        <TabsContent value="one">Content One</TabsContent>
        <TabsContent value="two">Content Two</TabsContent>
      </Tabs>,
    );
  }

  it("renders the default tab content", () => {
    renderTabs();
    expect(screen.getByText("Content One")).toBeInTheDocument();
    expect(screen.queryByText("Content Two")).not.toBeInTheDocument();
  });

  it("switches content when tab is clicked", async () => {
    renderTabs();
    await userEvent.click(screen.getByText("Tab Two"));
    expect(screen.getByText("Content Two")).toBeInTheDocument();
    expect(screen.queryByText("Content One")).not.toBeInTheDocument();
  });

  it("highlights the active tab", () => {
    renderTabs();
    expect(screen.getByText("Tab One")).toHaveClass("border-accent");
    expect(screen.getByText("Tab Two")).not.toHaveClass("border-accent");
  });

  it("updates active highlight on switch", async () => {
    renderTabs();
    await userEvent.click(screen.getByText("Tab Two"));
    expect(screen.getByText("Tab Two")).toHaveClass("border-accent");
    expect(screen.getByText("Tab One")).not.toHaveClass("border-accent");
  });
});
