import { render, screen } from "@testing-library/react";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "./table";

describe("Table", () => {
  function renderTable() {
    return render(
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Value</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow>
            <TableCell>Alpha</TableCell>
            <TableCell>100</TableCell>
          </TableRow>
        </TableBody>
      </Table>,
    );
  }

  it("renders table headers", () => {
    renderTable();
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Value")).toBeInTheDocument();
  });

  it("renders table cells", () => {
    renderTable();
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("100")).toBeInTheDocument();
  });

  it("wraps in overflow container", () => {
    renderTable();
    const table = screen.getByRole("table");
    expect(table.parentElement).toHaveClass("overflow-auto");
  });
});
