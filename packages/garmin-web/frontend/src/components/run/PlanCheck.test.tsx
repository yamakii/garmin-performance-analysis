import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import PlanCheck, { formatOverTime } from "./PlanCheck";
import type { RunPlan } from "../../types";

const PLAN: RunPlan = {
  verdict: "🟡",
  title: "ロング 22km",
  checks: [
    {
      axis: "intensity",
      target: "long_run",
      actual: "long_run",
      status: "on_plan",
      on_plan: true,
    },
    {
      axis: "volume",
      target: "22.0km",
      actual: "22.14km",
      status: "on_plan",
      on_plan: true,
    },
    {
      axis: "hr_ceiling",
      target: "≦150bpm",
      actual: "148bpm",
      status: "off_plan",
      on_plan: false,
    },
  ],
  hr_ceiling: { bpm: 150, seconds_over: 321, pct_over: 12.4 },
};

describe("PlanCheck", () => {
  it("test_plan_check_hidden_without_plan", () => {
    const { container } = render(<PlanCheck plan={null} />);

    // A day with no prescription has nothing to check against: the block is
    // absent rather than empty.
    expect(screen.queryByText("計画との照合")).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });

  it("test_plan_check_is_a_grid_with_status_in_each_row", () => {
    const { container } = render(<PlanCheck plan={PLAN} />);

    // A table pushed the 状態 column — the answer the reader came for — off a
    // 400px screen, so the card is a grid whose rows stack instead (#1252).
    expect(container.querySelector("table")).toBeNull();

    const rows = screen.getAllByRole("group");
    expect(rows.map((row) => row.getAttribute("aria-label"))).toEqual([
      "強度",
      "量",
      "心拍上限",
    ]);
    expect(within(rows[0]).getByText("計画どおり")).toBeInTheDocument();
    expect(within(rows[1]).getByText("計画どおり")).toBeInTheDocument();

    const ceilingRow = rows[2];
    const flag = within(ceilingRow).getByText("ずれ");
    expect(flag).toHaveClass("text-status-warn");
    // The over-ceiling bar reads as part of what actually happened, so it
    // belongs to the 実績 cell rather than to a column of its own.
    const actualCell = within(ceilingRow).getByText("148bpm")
      .parentElement as HTMLElement;
    expect(actualCell).toHaveTextContent("実績");
    expect(within(actualCell).getByText(/超過 5:21/)).toBeInTheDocument();
  });

  it("test_plan_check_header_and_rows_share_one_grid", () => {
    render(<PlanCheck plan={PLAN} />);

    const rows = screen.getAllByRole("group");
    const header = screen.getByText("状態").parentElement as HTMLElement;
    const grid = header.parentElement as HTMLElement;

    // One grid for the whole block: the header cells and every row's cells are
    // `display: contents` inside it, so the four tracks are measured once. Per
    // row grids sized their own columns and put 計画どおり under 目標 (#1270).
    expect(rows.every((row) => row.parentElement === grid)).toBe(true);
    expect(grid.className).toContain(
      "md:grid-cols-[96px_minmax(0,1fr)_minmax(0,1.5fr)_72px]",
    );
    expect(header.className).toContain("md:contents");
    for (const row of rows) {
      expect(row.className).toContain("md:contents");
      // No row may re-declare tracks of its own at `md`+.
      expect(row.className).not.toMatch(/md:grid-cols-/);
    }

    // The status cell is last in the DOM, so the shared grid drops it into the
    // 状態 column without an explicit column start.
    const cells = Array.from(rows[0].children);
    expect(cells).toHaveLength(4);
    expect(cells[3]).toHaveTextContent("計画どおり");
  });

  it("test_plan_check_stacked_layout_unchanged_below_md", () => {
    render(<PlanCheck plan={PLAN} />);

    const rows = screen.getAllByRole("group");
    // Below `md` the row is its own two-column grid and the tag is ordered up
    // onto the name's line — that is what keeps it on a 400px screen.
    for (const row of rows) {
      expect(row.className).toContain("grid-cols-[minmax(0,1fr)_auto]");
    }
    const tagCell = within(rows[2]).getByText("ずれ").parentElement as HTMLElement;
    expect(tagCell.className).toContain("order-2");
    expect(tagCell.className).toContain("justify-self-end");
    // The name keeps the first slot, the two readings follow it.
    expect(
      (within(rows[2]).getByText("心拍上限") as HTMLElement).className,
    ).toContain("order-1");
    expect(
      (within(rows[2]).getByText("≦150bpm").parentElement as HTMLElement)
        .className,
    ).toContain("order-3");
  });

  it("states a run that never touched the cap", () => {
    render(
      <PlanCheck
        plan={{
          ...PLAN,
          hr_ceiling: { bpm: 150, seconds_over: 0, pct_over: 0 },
        }}
      />,
    );

    expect(screen.getByText("超過なし")).toBeInTheDocument();
  });

  it("test_format_over_time_reads_as_a_length", () => {
    // A length of time, not a clock reading: "00:02" looks like a timestamp.
    expect(formatOverTime(321)).toBe("5:21");
    expect(formatOverTime(2)).toBe("0:02");
    expect(formatOverTime(3849)).toBe("1:04:09");
  });
});
