import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { PlanActivity, PlanDay, Prescription } from "../../types";
import DayCell from "./DayCell";

function prescription(overrides: Partial<Prescription> = {}): Prescription {
  return {
    prescription_id: 1,
    session_type: "easy",
    title: "イージー 8km",
    target_km: 8,
    target_minutes: null,
    hr_high: 145,
    status: "prescribed",
    ...overrides,
  };
}

const ACTIVITY: PlanActivity = {
  activity_id: 9000000103,
  activity_name: "ジョグ",
  total_distance_km: 8.2,
  avg_pace_seconds_per_km: 378.5,
  avg_heart_rate: 141,
};

function day(overrides: Partial<PlanDay> = {}): PlanDay {
  return {
    date: "2026-09-15",
    in_month: true,
    prescriptions: [],
    activities: [],
    ...overrides,
  };
}

/** The cell element itself, which carries the state's background. */
function cell(): HTMLElement {
  return screen.getByRole("cell");
}

describe("DayCell", () => {
  it("test_day_cell_states", () => {
    // Replaced: the original session is struck and the substitute follows it,
    // both inside the 注意 tint.
    const { rerender } = render(
      <DayCell
        day={day({
          prescriptions: [prescription({ status: "replaced" })],
          activities: [ACTIVITY],
        })}
      />,
    );
    expect(cell().className).toContain("bg-warn-tint");
    expect(cell().querySelector("s")?.textContent).toBe("イージー 8km ≤145");
    expect(screen.getByText("→ 8.2 · 6:19 · 141")).toBeInTheDocument();

    // Skipped: no badge, the name and its target are struck through.
    rerender(
      <DayCell day={day({ prescriptions: [prescription({ status: "skipped" })] })} />,
    );
    expect(screen.getByText("イージー").className).toContain("line-through");
    expect(screen.getByText("8km ≤145").className).toContain("line-through");

    // Outside the month the cell keeps its place but stops competing.
    rerender(<DayCell day={day({ in_month: false })} />);
    expect(cell().className).toContain("text-ink-faint");

    // A week with no prescriptions still states the block's ladder target on
    // its long-run column.
    rerender(
      <DayCell
        day={day({ date: "2026-09-27" })}
        ladderStep={{ week_start: "2026-09-21", target_km: 16, hr_ceiling: 150 }}
      />,
    );
    expect(screen.getByText("ロング目標")).toBeInTheDocument();
    expect(screen.getByText("16km ≤150")).toBeInTheDocument();
  });

  it("states what was run under a bold name once the session is done", () => {
    render(
      <DayCell
        day={day({
          prescriptions: [prescription({ session_type: "long", status: "done" })],
          activities: [ACTIVITY],
        })}
      />,
    );

    expect(screen.getByText("ロング").className).toContain("font-bold");
    expect(screen.getByText("8.2 · 6:19 · 141")).toBeInTheDocument();
    // The status is the presence of the actual row, not a badge.
    expect(screen.queryByText("実施")).toBeNull();
  });

  it("tints a rest directive and quotes its reason", () => {
    render(
      <DayCell
        day={day({
          prescriptions: [
            prescription({
              session_type: "rest",
              target_km: null,
              hr_high: null,
              rationale: "HRV が2夜連続で基準割れ。",
            }),
          ],
        })}
      />,
    );

    expect(cell().className).toContain("bg-warn-tint");
    expect(screen.getByText("休養").className).toContain("text-status-warn");
    expect(screen.getByText("HRV が2夜連続で基準割れ。")).toBeInTheDocument();
  });

  it("shows strides add-on", () => {
    // An easy run with strides states the add-on after its target (#1298).
    render(
      <DayCell
        day={day({
          prescriptions: [
            prescription({
              target_km: null,
              target_minutes: 35,
              strides: { reps: 4, run_seconds: 20, recovery_seconds: 60 },
            }),
          ],
        })}
      />,
    );

    expect(cell()).toHaveTextContent("流し4本");
    expect(screen.getByText("35分 ≤145 ＋流し4本")).toBeInTheDocument();
  });

  it("shows purpose label", () => {
    // A long run rehearsing goal pace is named for its purpose (#1315); a long
    // run without one keeps the plain session label.
    const { rerender } = render(
      <DayCell
        day={day({
          prescriptions: [
            prescription({ session_type: "long", purpose: "long_goal_pace" }),
          ],
        })}
      />,
    );
    expect(screen.getByText("MPロング").className).toContain("font-bold");
    expect(screen.queryByText("ロング")).toBeNull();

    rerender(
      <DayCell
        day={day({
          prescriptions: [
            prescription({ session_type: "long", purpose: "long_easy" }),
          ],
        })}
      />,
    );
    expect(screen.getByText("ロング")).toBeInTheDocument();
  });

  it("marks today with an accent tint and a TODAY tag", () => {
    render(<DayCell day={day()} isToday />);

    expect(cell().className).toContain("bg-accent-tint");
    expect(screen.getByText("TODAY")).toBeInTheDocument();
  });
});
