import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { makeMonthPlan } from "../../test/planFixture";
import MonthGrid from "./MonthGrid";

function renderGrid(weekStartDay = 0, today = new Date(2026, 8, 13)) {
  return render(
    <MemoryRouter>
      <MonthGrid plan={makeMonthPlan("2026-09", weekStartDay)} today={today} />
    </MemoryRouter>,
  );
}

describe("MonthGrid", () => {
  it("test_month_grid_weekday_header_order", () => {
    renderGrid();

    const [header] = screen.getAllByRole("rowgroup");
    const columns = within(header).getAllByRole("columnheader");
    // The week column, then the seven days from the configured start day: a
    // Monday-start week puts the Sunday long run in the last column.
    expect(columns.map((c) => c.textContent)).toEqual([
      "週",
      "月",
      "火",
      "水",
      "木",
      "金",
      "土",
      "日",
    ]);

    // Five week rows for September 2026 (08-31 .. 10-04).
    const [, body] = screen.getAllByRole("rowgroup");
    expect(within(body).getAllByRole("row")).toHaveLength(5);
  });

  it("reorders the header for a Sunday-start week", () => {
    renderGrid(6);

    const [header] = screen.getAllByRole("rowgroup");
    const columns = within(header).getAllByRole("columnheader");
    expect(columns[1].textContent).toBe("日");
    expect(columns[7].textContent).toBe("土");
  });

  it("test_month_grid_highlights_today", () => {
    renderGrid(0, new Date(2026, 8, 13));

    const marker = screen.getByText("今日");
    // The marker sits in the 9/13 cell, next to that day's prescription.
    const cell = marker.closest("td");
    expect(cell).not.toBeNull();
    expect(within(cell as HTMLElement).getByText("ロング")).toBeInTheDocument();
    expect(within(cell as HTMLElement).getByText("13")).toBeInTheDocument();
  });

  it("links every week row to its review and states adherence", () => {
    renderGrid();

    expect(screen.getByRole("link", { name: "9/7週" })).toHaveAttribute(
      "href",
      "/weekly-reviews/2026-09-07",
    );
    // 9/7 week: both prescribed sessions done.
    expect(screen.getByText("2/2 実施")).toBeInTheDocument();
    // 9/14 week: two done, one skipped, one still pending.
    expect(screen.getByText("2/4 実施")).toBeInTheDocument();
  });

  it("shows the ladder target on a long-run day with no prescription", () => {
    renderGrid();

    // The 9/21 cutback week has a 16km ladder step and no prescription rows,
    // as does the 8/31 week (19km) — both state the target on their last
    // column, which is the long-run day of a Monday-start week.
    expect(screen.getAllByText("ロング目標")).toHaveLength(2);
    expect(screen.getByText("16km")).toBeInTheDocument();
    expect(screen.getByText("19km")).toBeInTheDocument();
  });

  it("renders the actual run beside the prescription", () => {
    renderGrid();

    expect(screen.getByText("21.4km 6:19/km")).toBeInTheDocument();
  });
});
