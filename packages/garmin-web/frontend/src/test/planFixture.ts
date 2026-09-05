import type {
  Adherence,
  LadderStep,
  MonthPlan,
  PlanActivity,
  PlanDay,
  PlanWeek,
  Prescription,
} from "../types";
import { weekRowsForMonth } from "../utils/week";

/**
 * The September 2026 month-plan payload shared by the plan tests.
 *
 * Mirrors the backend fixture in `tests/conftest.py`: 9/1 is a Tuesday, so a
 * Monday-start grid runs 2026-08-31 .. 2026-10-04 (5 rows); the 9/7 week is
 * reviewed and fully done, the 9/14 week is half resolved, and the 9/21 week is
 * a cutback whose long run exists only as a ladder step.
 */

const PRESCRIPTIONS: Record<string, Prescription[]> = {
  "2026-09-08": [
    {
      prescription_id: 1,
      session_type: "easy",
      title: "イージー 8km",
      target_km: 8,
      target_minutes: null,
      hr_high: 145,
      status: "done",
    },
  ],
  "2026-09-13": [
    {
      prescription_id: 2,
      session_type: "long",
      title: "ロング 22km",
      target_km: 22,
      target_minutes: 150,
      hr_high: 150,
      status: "done",
    },
  ],
  "2026-09-15": [
    {
      prescription_id: 4,
      session_type: "easy",
      title: "イージー 8km",
      target_km: 8,
      target_minutes: null,
      hr_high: 145,
      status: "done",
    },
  ],
  "2026-09-17": [
    {
      prescription_id: 5,
      session_type: "tempo",
      title: "テンポ 6km",
      target_km: 6,
      target_minutes: null,
      hr_high: 168,
      status: "done",
    },
  ],
  "2026-09-18": [
    {
      prescription_id: 6,
      session_type: "easy",
      title: "イージー 6km",
      target_km: 6,
      target_minutes: null,
      hr_high: 145,
      status: "skipped",
    },
  ],
  "2026-09-20": [
    {
      prescription_id: 7,
      session_type: "long",
      title: "ロング 25km",
      target_km: 25,
      target_minutes: null,
      hr_high: 150,
      status: "prescribed",
    },
  ],
};

const ACTIVITIES: Record<string, PlanActivity[]> = {
  "2026-09-13": [
    {
      activity_id: 9000000103,
      activity_name: "ロングラン",
      total_distance_km: 21.4,
      avg_pace_seconds_per_km: 378.5,
      avg_heart_rate: 146,
    },
  ],
};

const LADDER: Record<string, LadderStep> = {
  "2026-08-31": { week_start: "2026-08-31", target_km: 19 },
  "2026-09-07": { week_start: "2026-09-07", target_km: 22, hr_ceiling: 150 },
  "2026-09-14": { week_start: "2026-09-14", target_km: 25 },
  "2026-09-21": { week_start: "2026-09-21", target_km: 16, kind: "cutback" },
};

const REVIEWED_WEEKS = ["2026-09-07"];

/** Mirrors `summarize_adherence`: `prescribed` is the row count. */
function adherenceOf(rows: Prescription[]): Adherence {
  const summary: Adherence = {
    prescribed: rows.length,
    done: 0,
    replaced: 0,
    skipped: 0,
    pending: 0,
  };
  for (const row of rows) {
    if (row.status === "done") summary.done += 1;
    else if (row.status === "replaced") summary.replaced += 1;
    else if (row.status === "skipped") summary.skipped += 1;
    else summary.pending += 1;
  }
  return summary;
}

export function makeMonthPlan(month = "2026-09", weekStartDay = 0): MonthPlan {
  const inMonth = (date: string) => date.slice(0, 7) === month;
  const weeks: PlanWeek[] = weekRowsForMonth(month, weekStartDay).map((row) => {
    const days: PlanDay[] = row.days.map((date) => ({
      date,
      in_month: inMonth(date),
      prescriptions: PRESCRIPTIONS[date] ?? [],
      activities: ACTIVITIES[date] ?? [],
    }));
    return {
      week_start: row.weekStart,
      week_end: row.days[6],
      in_month: days.every((day) => day.in_month),
      ladder_step: LADDER[row.weekStart] ?? null,
      review_exists: REVIEWED_WEEKS.includes(row.weekStart),
      adherence: adherenceOf(days.flatMap((day) => day.prescriptions)),
      days,
    };
  });

  return {
    month,
    week_start_day: weekStartDay,
    weeks,
    blocks: [
      {
        block_id: 2,
        phase: "build",
        title: "新潟マラソン ビルド",
        start_date: "2026-08-24",
        end_date: "2026-10-11",
        weight_mode: "微減",
        quality_sessions_per_week: 2,
      },
    ],
    adherence: adherenceOf(
      weeks
        .flatMap((week) => week.days)
        .filter((day) => day.in_month)
        .flatMap((day) => day.prescriptions),
    ),
  };
}
