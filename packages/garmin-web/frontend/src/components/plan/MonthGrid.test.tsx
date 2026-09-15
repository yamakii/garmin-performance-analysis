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

    const marker = screen.getByText("TODAY");
    const cell = marker.closest('[role="cell"]') as HTMLElement;
    expect(cell).not.toBeNull();
    expect(cell.className).toContain("bg-accent-tint");
    // The session that was run states its name in bold and what it came to.
    expect(within(cell).getByText("ロング").className).toContain("font-bold");
    expect(within(cell).getByText("21.4 · 6:19 · 146")).toBeInTheDocument();
    expect(within(cell).getByText("13")).toBeInTheDocument();
  });

  it("test_week_header_adherence_text", () => {
    renderGrid();

    // 9/7: both prescribed sessions done, so nothing is coloured.
    const reviewed = screen.getByText("2/2 実施");
    expect(reviewed).toHaveAttribute("data-tone", "good");
    expect(reviewed.className).not.toContain("text-status");
    // 9/14: two done, one skipped, one still ahead — an unfinished week.
    expect(screen.getByText("2/4 · 進行中")).toBeInTheDocument();
    // A prescribed week states the distance it adds up to (8+6+6+25).
    expect(screen.getByText("計画 45km")).toBeInTheDocument();

    // 9/21 is a cutback week that so far exists only as a ladder step.
    const cutback = screen
      .getByRole("link", { name: "9/21週" })
      .closest('[role="rowheader"]') as HTMLElement;
    expect(within(cutback).getByText("未処方")).toBeInTheDocument();
    expect(within(cutback).getByText("ロング 16km")).toBeInTheDocument();
  });

  it("links every week row to its review", () => {
    renderGrid();

    expect(screen.getByRole("link", { name: "9/7週" })).toHaveAttribute(
      "href",
      "/weekly-reviews/2026-09-07",
    );
    // The reviewed week is the one carrying the accent.
    expect(screen.getByRole("link", { name: "9/7週" }).className).toContain(
      "text-accent",
    );
    expect(screen.getByRole("link", { name: "9/14週" }).className).toContain(
      "text-ink",
    );
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

  it("test_month_grid_rows_use_minmax_columns", () => {
    renderGrid();

    // Header row + five week rows: every one of them is its own grid, so they
    // only line up while their day tracks are free to shrink. `1fr` is
    // `minmax(auto, 1fr)`, which lets one unbreakable token widen a column on
    // a single row and knock that row out of step with the header (#1143).
    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(6);
    for (const row of rows) {
      expect(row.className).toContain("minmax(0,1fr)");
      expect(row.className).not.toContain("repeat(7,1fr)");
    }
  });

  it("test_month_grid_scrolls_its_bands_with_the_days", () => {
    render(
      <MemoryRouter>
        <MonthGrid
          plan={makeMonthPlan("2026-09", 0)}
          today={new Date(2026, 8, 13)}
          bands={<p>ビルド · 新潟マラソン ビルド</p>}
        />
      </MemoryRouter>,
    );

    // The bands share the grid's columns, so they share its scroller.
    const band = screen.getByText("ビルド · 新潟マラソン ビルド");
    const scroller = band.closest(".overflow-x-auto");
    expect(scroller).not.toBeNull();
    expect(scroller).toContainElement(
      screen.getByRole("table", { name: "月間プラン" }),
    );
  });

  it("explains the grid's states in one legend line", () => {
    renderGrid();

    expect(screen.getByText(/太字 \+ 実績行/)).toBeInTheDocument();
  });
});
