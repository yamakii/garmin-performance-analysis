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
