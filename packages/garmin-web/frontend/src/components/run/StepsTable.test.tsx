import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import StepsTable, { formatStepDuration } from "./StepsTable";
import type { RunFlowStep } from "../../types";

function step(
  id: string,
  label: string,
  values: Partial<RunFlowStep> = {},
): RunFlowStep {
  return {
    id,
    role: "run",
    label_ja: label,
    short_ja: label,
    rep_no: null,
    split_from: 1,
    split_to: 1,
    start_km: 0,
    end_km: 0,
    start_s: 0,
    end_s: 0,
    distance_km: 0,
    duration_s: 0,
    pace_s_per_km: null,
    avg_hr: null,
    max_hr: null,
    is_long: false,
    ...values,
  };
}

describe("StepsTable", () => {
  it("test_steps_table_lists_a_row_per_step", () => {
    render(
      <StepsTable
        steps={[
          step("s1", "ウォームアップ", {
            distance_km: 2,
            duration_s: 840,
            pace_s_per_km: 420,
            avg_hr: 124,
            max_hr: 132,
          }),
          step("s2", "1本目", {
            distance_km: 1.11,
            duration_s: 360,
            pace_s_per_km: 324,
            avg_hr: 170,
            max_hr: 175,
          }),
          step("s3", "レスト1", {
            distance_km: 0.18,
            duration_s: 120,
            pace_s_per_km: 667,
            avg_hr: 150,
            max_hr: 168,
          }),
        ]}
      />,
    );

    const rows = within(screen.getByRole("table")).getAllByRole("row");
    expect(rows).toHaveLength(4);
    const rep = within(rows[2]).getAllByRole("cell");
    // The rep as it was run — 1.0 + 0.11 km is one 1.11 km rep, not two laps.
    expect(rep.map((cell) => cell.textContent)).toEqual([
      "1本目",
      "1.11",
      "6:00",
      "5:24/km",
      "170",
      "175",
    ]);
    expect(
      within(screen.getByRole("table")).getAllByRole("columnheader").map(
        (header) => header.textContent,
      ),
    ).toEqual(["区間", "KM", "時間", "ペース", "平均心拍", "最大心拍"]);
  });

  it("test_step_duration_reads_as_a_clock", () => {
    // A column of rests is read in minutes; "06:00" pads for no one.
    expect(formatStepDuration(360)).toBe("6:00");
    expect(formatStepDuration(120)).toBe("2:00");
    expect(formatStepDuration(45)).toBe("0:45");
    expect(formatStepDuration(3870)).toBe("1:04:30");
    expect(formatStepDuration(null)).toBe("-");
  });
});
