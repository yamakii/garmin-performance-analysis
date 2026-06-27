import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import WeeklyReviewDetail from "./WeeklyReviewDetail";
import type { WeeklyReviewData } from "../types";

function renderDetail(reviewData: WeeklyReviewData) {
  const versions = [
    {
      review_id: 1,
      user_id: "default",
      week_start_date: "2026-06-15",
      week_end_date: "2026-06-21",
      review_date: "2026-06-22",
      review_data: reviewData,
      created_at: null,
      agent_name: "weekly-review",
      agent_version: "1.0",
    },
  ];
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify(versions), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );
  return render(
    <MemoryRouter initialEntries={["/weekly-reviews/2026-06-15"]}>
      <Routes>
        <Route
          path="/weekly-reviews/:weekStart"
          element={<WeeklyReviewDetail />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("WeeklyReviewDetail", () => {
  it("test_renders_garmin_next_week_table", async () => {
    renderDetail({
      garmin_next_week: [
        { date: "2026-06-22", title: "Easy Run", type: "easy" },
        { date: "2026-06-24", title: "Interval", type: "anaerobic" },
      ],
    });

    expect(
      await screen.findByText("来週のGarminワークアウト"),
    ).toBeInTheDocument();
    expect(screen.getByText("2026-06-22")).toBeInTheDocument();
    expect(screen.getByText("Easy Run")).toBeInTheDocument();
    expect(screen.getByText("easy")).toBeInTheDocument();
    expect(screen.getByText("2026-06-24")).toBeInTheDocument();
    expect(screen.getByText("Interval")).toBeInTheDocument();
    expect(screen.getByText("anaerobic")).toBeInTheDocument();
  });

  it("test_renders_intensity_distribution", async () => {
    renderDetail({
      this_week: {
        volume_km: 35.5,
        intensity_distribution: { easy_z1_z2: 4, long_run: 1 },
      },
    });

    expect(await screen.findByText("実績サマリー")).toBeInTheDocument();
    expect(screen.getByText("easy_z1_z2: 4")).toBeInTheDocument();
    expect(screen.getByText("long_run: 1")).toBeInTheDocument();
  });

  it("test_renders_weight_tracking_section", async () => {
    renderDetail({
      weight_tracking: {
        recent_median_kg: 79.6,
        bmi: 24.1,
        trend: "微減",
      },
    });

    expect(await screen.findByText("体重トラッキング")).toBeInTheDocument();
    expect(screen.getByText(/79\.6/)).toBeInTheDocument();
    expect(screen.getByText(/24\.1/)).toBeInTheDocument();
    expect(screen.getByText("微減")).toBeInTheDocument();
  });

  it("test_renders_continuity_note", async () => {
    renderDetail({
      continuity_note: "前回からの継続性は良好です。",
    });

    expect(await screen.findByText("前回からの継続性")).toBeInTheDocument();
    expect(
      screen.getByText("前回からの継続性は良好です。"),
    ).toBeInTheDocument();
  });

  it("test_omits_absent_optional_sections", async () => {
    renderDetail({
      this_week: { volume_km: 35.5, run_count: 4 },
      overall: "順調です。",
    });

    // 実績サマリー is always present; the optional sections must not render.
    expect(await screen.findByText("実績サマリー")).toBeInTheDocument();
    expect(
      screen.queryByText("来週のGarminワークアウト"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("体重トラッキング")).not.toBeInTheDocument();
    expect(screen.queryByText("リカバリー")).not.toBeInTheDocument();
    expect(screen.queryByText("前回からの継続性")).not.toBeInTheDocument();
    expect(screen.queryByText("週次ランプ")).not.toBeInTheDocument();
  });
});
