import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ActivityDetailResponse } from "../types";
import HeroHeader from "./HeroHeader";

// Real-schema mock mirroring the L3 fixture (activity 20636804823).
const DETAIL: ActivityDetailResponse = {
  activity: {
    activity_id: 20636804823,
    activity_date: "2025-10-09",
    activity_name: "Morning Run",
    total_distance_km: 5.66,
    total_time_seconds: 2186,
    avg_pace_seconds_per_km: 386.0,
    avg_heart_rate: 144,
  },
  splits: [],
  form_efficiency: null,
  hr_zones: [],
  performance_trends: null,
  form_evaluations: null,
  vo2_max: { value: 50.1, date: "2025-10-09" },
  lactate_threshold: { heart_rate: 168, speed_mps: 3.2, date_hr: "2025-10-09" },
};

describe("HeroHeader", () => {
  it("HeroHeader renders activity name as heading with KPI strip", () => {
    render(<HeroHeader detail={DETAIL} starRating="★★★★☆ 4.3/5.0" />);

    // Activity name is the page headline (h1)
    expect(
      screen.getByRole("heading", { level: 1, name: "Morning Run" }),
    ).toBeInTheDocument();

    // Date appears inline with the headline
    expect(screen.getByText("2025-10-09")).toBeInTheDocument();

    // Gold star rating from the summary section
    expect(screen.getByLabelText("評価 4.3 / 5.0")).toBeInTheDocument();

    // KPI strip: distance (number only) and pace (without /km suffix)
    expect(screen.getByText("距離")).toBeInTheDocument();
    expect(screen.getByText("5.66")).toBeInTheDocument();
    expect(screen.getByText("平均ペース")).toBeInTheDocument();
    expect(screen.getByText("6:26")).toBeInTheDocument();
    expect(screen.getByText("平均心拍")).toBeInTheDocument();
    expect(screen.getByText("144")).toBeInTheDocument();

    // Physiology sub-row
    expect(screen.getByText("VO2 Max")).toBeInTheDocument();
    expect(screen.getByText("50.1")).toBeInTheDocument();
  });

  it("falls back to a placeholder name and omits absent KPIs", () => {
    render(
      <HeroHeader
        detail={{
          ...DETAIL,
          activity: {
            ...DETAIL.activity,
            activity_name: null,
            avg_pace_seconds_per_km: null,
          },
          vo2_max: null,
          lactate_threshold: null,
        }}
        starRating={null}
      />,
    );

    expect(
      screen.getByRole("heading", { level: 1, name: "アクティビティ" }),
    ).toBeInTheDocument();
    // Absent pace renders as "-"; no physiology sub-row
    expect(screen.queryByText("VO2 Max")).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/評価/)).not.toBeInTheDocument();
  });
});
