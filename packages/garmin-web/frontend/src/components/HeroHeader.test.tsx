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
  // Garmin %LTHR zones on the configured LTHR 170: zone 5 opens at 100% of it.
  hr_zones: [
    { zone_number: 1, zone_low_boundary: 110, zone_high_boundary: 135 },
    { zone_number: 2, zone_low_boundary: 136, zone_high_boundary: 150 },
    { zone_number: 3, zone_low_boundary: 151, zone_high_boundary: 161 },
    { zone_number: 4, zone_low_boundary: 162, zone_high_boundary: 169 },
    { zone_number: 5, zone_low_boundary: 170, zone_high_boundary: 220 },
  ].map((zone) => ({
    ...zone,
    activity_id: 20636804823,
    time_in_zone_seconds: 0,
    zone_percentage: 0,
  })),
  performance_trends: null,
  form_evaluations: null,
  vo2_max: { value: 50.1, date: "2025-10-09" },
  // Garmin's auto-detected estimate, which disagrees with the configured 170.
  lactate_threshold: { heart_rate: 164, speed_mps: 3.0278, date_hr: "2026-07-11" },
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
          hr_zones: [],
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
    expect(screen.queryByText(/乳酸閾値/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/評価/)).not.toBeInTheDocument();
  });

  // The threshold in the header must be the one configured on the watch — the
  // value the zones and the prescriptions are built on — not Garmin's
  // auto-detected estimate, which disagrees with it and goes stale (#1098).
  it("shows the configured threshold taken from the zone 5 lower bound", () => {
    render(<HeroHeader detail={DETAIL} starRating={null} />);

    expect(screen.getByText("乳酸閾値（設定値）")).toBeInTheDocument();
    expect(screen.getByText("170 bpm")).toBeInTheDocument();
  });

  it("never shows Garmin's auto-detected threshold estimate", () => {
    render(<HeroHeader detail={DETAIL} starRating={null} />);

    // 164 bpm / 5:30/km is the estimate carried on the same response.
    expect(screen.queryByText("164 bpm")).not.toBeInTheDocument();
    expect(screen.queryByText(/5:30/)).not.toBeInTheDocument();
    expect(screen.queryByText(/推定/)).not.toBeInTheDocument();
  });

  it("omits the threshold when the activity carries no zone 5", () => {
    render(
      <HeroHeader
        detail={{ ...DETAIL, hr_zones: DETAIL.hr_zones.slice(0, 4) }}
        starRating={null}
      />,
    );

    expect(screen.queryByText(/乳酸閾値/)).not.toBeInTheDocument();
    // The rest of the sub-row survives.
    expect(screen.getByText("VO2 Max")).toBeInTheDocument();
  });

  it("omits the threshold when the activity has no zones at all", () => {
    render(
      <HeroHeader detail={{ ...DETAIL, hr_zones: [] }} starRating={null} />,
    );

    expect(screen.queryByText(/乳酸閾値/)).not.toBeInTheDocument();
  });
});
