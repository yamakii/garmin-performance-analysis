import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { makeMonthPlan } from "../../test/planFixture";
import type { PlanWeek, Prescription } from "../../types";
import WeekStrip from "./WeekStrip";

const WEEK = makeMonthPlan().weeks[1];
const DAYS = WEEK.days.map((day) => day.date);

/** A week of `WEEK`'s shape with the given prescriptions swapped in. */
function weekWith(rows: Record<string, Prescription[]>): PlanWeek {
  return {
    ...WEEK,
    days: WEEK.days.map((day) => ({
      ...day,
      prescriptions: rows[day.date] ?? [],
      activities: [],
    })),
  };
}

function cellFor(date: string): HTMLElement {
  const index = DAYS.indexOf(date);
  return screen.getAllByRole("listitem")[index];
}

describe("WeekStrip", () => {
  it("test_week_strip_seven_cells_today_and_rest", () => {
    render(<WeekStrip week={WEEK} days={DAYS} today="2026-09-13" />);

    expect(screen.getAllByRole("listitem")).toHaveLength(7);

    // Today is the only tinted, accented cell.
    const today = cellFor("2026-09-13");
    expect(today).toHaveClass("bg-accent-tint");
    expect(within(today).getByText("TODAY")).toBeInTheDocument();
    const dateLine = today.querySelector("p");
    expect(dateLine).toHaveTextContent("13 日");
    expect(dateLine).toHaveClass("font-semibold", "text-accent");
    // The long run was done, so the cell states the actual, not the target.
    expect(within(today).getByText("ロング 22km")).toHaveClass("font-bold");
    expect(within(today).getByText("21.4km · 6:19 · 146")).toHaveClass(
      "text-ink",
    );

    // A day with no prescription is a rest day, stated but not shouted.
    const rest = cellFor("2026-09-12");
    expect(within(rest).getByText("休養")).toHaveClass("text-ink-muted");
    expect(rest.className).not.toMatch(/bg-(accent|warn)-tint/);

    // A prescribed easy day names the session and its target.
    const easy = cellFor("2026-09-08");
    expect(within(easy).getByText("イージー 8km")).toHaveClass("font-bold");
  });

  it("test_week_strip_replaced_and_rest_directive", () => {
    const week = weekWith({
      "2026-09-09": [
        {
          prescription_id: 11,
          session_type: "tempo",
          title: "テンポ 6km",
          target_km: 6,
          target_minutes: null,
          hr_high: 168,
          status: "replaced",
        },
      ],
      "2026-09-10": [
        {
          prescription_id: 12,
          session_type: "rest",
          title: "完全休養",
          target_km: null,
          target_minutes: null,
          hr_high: null,
          rationale: "HRVが2夜連続で基準割れ",
          status: "prescribed",
        },
      ],
    });
    render(<WeekStrip week={week} days={DAYS} today="2026-09-13" />);

    // Replaced with nothing recorded: the strip can only say it was swapped.
    const replaced = cellFor("2026-09-09");
    expect(replaced).toHaveClass("bg-warn-tint");
    expect(replaced.querySelector("s")).toHaveTextContent("テンポ 6km 6km ≤168");
    expect(within(replaced).getByText("→ 代替")).toBeInTheDocument();

    // A rest directive is a decision, so it carries the same 注意 tint.
    const rest = cellFor("2026-09-10");
    expect(rest).toHaveClass("bg-warn-tint");
    expect(within(rest).getByText("休養")).toHaveClass(
      "font-bold",
      "text-status-warn",
    );
    expect(within(rest).getByText("HRVが2夜連続で基準割れ")).toHaveClass(
      "text-status-warn",
    );
  });

  it("test_week_strip_replaced_states_what_was_run", () => {
    // A swapped session with a recorded run: the strip states what actually
    // happened, the same `km · pace · hr` shape DayCell uses, rather than the
    // bare "代替" that left the reader with no idea what replaced it (#1192).
    const week = weekWith({
      "2026-09-09": [
        {
          prescription_id: 11,
          session_type: "tempo",
          title: "テンポ 6km",
          target_km: 6,
          target_minutes: null,
          hr_high: 168,
          status: "replaced",
        },
      ],
    });
    const withActual: PlanWeek = {
      ...week,
      days: week.days.map((day) =>
        day.date === "2026-09-09"
          ? {
              ...day,
              activities: [
                {
                  activity_id: 555,
                  activity_date: "2026-09-09",
                  activity_name: "Easy Run",
                  total_distance_km: 8.2,
                  avg_pace_seconds_per_km: 402,
                  avg_heart_rate: 139,
                },
              ],
            }
          : day,
      ),
    };
    render(<WeekStrip week={withActual} days={DAYS} today="2026-09-13" />);

    const replaced = cellFor("2026-09-09");
    expect(within(replaced).getByText("→ 8.2km · 6:42 · 139")).toBeInTheDocument();
    expect(within(replaced).queryByText("→ 代替")).not.toBeInTheDocument();
    // The prescription it replaced is still struck through above it.
    expect(replaced.querySelector("s")).toHaveTextContent("テンポ 6km");
  });

  it("test_week_strip_scrolls_horizontally", () => {
    render(<WeekStrip week={WEEK} days={DAYS} today="2026-09-13" />);

    // Seven cells never fit a phone's width. The strip keeps its columns and
    // scrolls sideways instead of squeezing a label down to one character per
    // line (#1143).
    const grid = screen.getByRole("list");
    expect(grid).toHaveClass("grid", "grid-cols-7", "min-w-[640px]");
    expect(grid.parentElement).toHaveClass("overflow-x-auto");
  });

  it("test_week_strip_rationale_wraps_anywhere", () => {
    const week = weekWith({
      "2026-09-10": [
        {
          prescription_id: 14,
          session_type: "rest",
          title: "完全休養",
          target_km: null,
          target_minutes: null,
          hr_high: null,
          rationale: "cutback_rule の extra_rest_days=1",
          status: "prescribed",
        },
      ],
    });
    render(<WeekStrip week={week} days={DAYS} today="2026-09-13" />);

    // `extra_rest_days=1` has no break opportunity of its own, so without
    // this it runs across the next cell's border.
    const rationale = screen.getByText("cutback_rule の extra_rest_days=1");
    expect(rationale.tagName).toBe("P");
    expect(rationale).toHaveClass("[overflow-wrap:anywhere]");
  });

  it("strikes a skipped session and renders an empty week", () => {
    const week = weekWith({
      "2026-09-11": [
        {
          prescription_id: 13,
          session_type: "easy",
          title: "イージー 6km",
          target_km: 6,
          target_minutes: null,
          hr_high: 145,
          status: "skipped",
        },
      ],
    });
    const { rerender } = render(
      <WeekStrip week={week} days={DAYS} today="2026-09-13" />,
    );
    expect(within(cellFor("2026-09-11")).getByText("イージー 6km")).toHaveClass(
      "line-through",
    );

    rerender(<WeekStrip week={null} days={DAYS} today="2026-09-13" />);
    expect(screen.getAllByRole("listitem")).toHaveLength(7);
    expect(screen.getAllByText("休養")).toHaveLength(7);
  });
});
