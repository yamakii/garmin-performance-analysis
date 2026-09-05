import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { PlanWeek, WeeklyReview } from "../../types";
import { makeMonthPlan } from "../../test/planFixture";
import ThisWeekPlan from "./ThisWeekPlan";

/** The 2026-09-07 week of the shared fixture: two prescriptions, both done. */
function prescribedWeek(): PlanWeek {
  return makeMonthPlan().weeks[1];
}

/** The 2026-08-31 week: inside the grid, but with no prescription rows. */
function unprescribedWeek(): PlanWeek {
  return makeMonthPlan().weeks[0];
}

function makeReview(
  reviewData: WeeklyReview["review_data"],
  overrides: Partial<WeeklyReview> = {},
): WeeklyReview {
  return {
    review_id: 1,
    user_id: "default",
    week_start_date: "2026-06-29",
    week_end_date: "2026-07-05",
    review_date: "2026-06-30",
    review_data: reviewData,
    created_at: "2026-06-30 21:00:00",
    agent_name: "weekly-review",
    agent_version: "1.3",
    ...overrides,
  };
}

function renderPlan(
  review: WeeklyReview | null,
  today?: Date,
  week: PlanWeek | null = null,
) {
  return render(
    <MemoryRouter>
      <ThisWeekPlan review={review} week={week} today={today} />
    </MemoryRouter>,
  );
}

describe("ThisWeekPlan", () => {
  it("renders verdict rows and highlights today's session", () => {
    const review = makeReview({
      verdict: [
        { date: "2026-07-01", session: "Tempo", rating: "🟡", comment: "様子見" },
        { date: "2026-07-02", session: "Recovery", rating: "⚪" },
        { date: "2026-07-05", session: "Long Run", rating: "✅", comment: "時間×HR管理" },
      ],
      recommendations: [],
    });

    renderPlan(review, new Date(2026, 6, 2));

    expect(screen.getByText("今週のプラン")).toBeInTheDocument();
    expect(screen.getByText("Tempo")).toBeInTheDocument();
    expect(screen.getByText("Recovery")).toBeInTheDocument();
    expect(screen.getByText("Long Run")).toBeInTheDocument();
    expect(screen.getByText("様子見")).toBeInTheDocument();
    // The 2026-07-02 row carries the 今日 marker.
    expect(screen.getByText("今日")).toBeInTheDocument();
  });

  it("test_this_week_plan_rating_accessible", () => {
    const review = makeReview({
      verdict: [
        { date: "2026-07-01", session: "Tempo", rating: "🟡" },
        { date: "2026-07-05", session: "Long Run", rating: "✅" },
        { date: "2026-07-06", session: "Rest" },
      ],
    });

    renderPlan(review, new Date(2026, 6, 2));

    // The rating carried the row's verdict while being hidden from assistive
    // tech; it is exposed with the word it stands for now (#912).
    const warn = screen.getByRole("img", { name: "注意" });
    expect(warn).toHaveTextContent("🟡");
    expect(warn).not.toHaveAttribute("aria-hidden");
    expect(screen.getByRole("img", { name: "良好" })).toHaveTextContent("✅");

    // The placeholder bullet on a rating-less row stays decorative.
    expect(screen.getAllByRole("img")).toHaveLength(2);
  });

  it("titles the card 直近レビューのプラン when today is outside the week", () => {
    const review = makeReview({
      verdict: [{ date: "2026-06-30", session: "Tempo", rating: "✅" }],
    });

    renderPlan(review, new Date(2026, 6, 10));

    expect(screen.getByText("直近レビューのプラン")).toBeInTheDocument();
    expect(screen.queryByText("今日")).not.toBeInTheDocument();
  });

  it("caps recommendations at two entries", () => {
    const review = makeReview({
      verdict: [{ date: "2026-07-01", session: "Base", rating: "✅" }],
      recommendations: ["一つ目の推奨", "二つ目の推奨", "三つ目の推奨"],
    });

    renderPlan(review, new Date(2026, 6, 2));

    expect(screen.getByText("一つ目の推奨")).toBeInTheDocument();
    expect(screen.getByText("二つ目の推奨")).toBeInTheDocument();
    expect(screen.queryByText("三つ目の推奨")).not.toBeInTheDocument();
  });

  it("falls back to the Garmin schedule when there are no verdict rows", () => {
    const review = makeReview({
      garmin_next_week: [
        { date: "2026-07-03", title: "Base", type: "fbtAdaptiveWorkout" },
        { date: "2026-07-05", title: "Long Run", type: "fbtAdaptiveWorkout" },
      ],
    });

    renderPlan(review, new Date(2026, 6, 2));

    expect(screen.getByText("Base")).toBeInTheDocument();
    expect(screen.getByText("Long Run")).toBeInTheDocument();
  });

  it("links to the full weekly review", () => {
    const review = makeReview({ verdict: [] });

    renderPlan(review, new Date(2026, 6, 2));

    expect(screen.getByRole("link", { name: "レビュー全文 →" })).toHaveAttribute(
      "href",
      "/weekly-reviews/2026-06-29",
    );
  });

  it("test_this_week_plan_prefers_prescriptions", () => {
    const review = makeReview({
      verdict: [{ date: "2026-09-08", session: "Tempo", rating: "✅" }],
      recommendations: ["ロング走は時間×HRで管理"],
    });

    renderPlan(review, new Date(2026, 8, 8), prescribedWeek());

    // The structured rows replace the prose verdict...
    expect(screen.getByText("イージー 8km")).toBeInTheDocument();
    expect(screen.getByText("ロング 22km")).toBeInTheDocument();
    expect(screen.queryByText("Tempo")).not.toBeInTheDocument();
    // ...with their target and lifecycle status.
    expect(screen.getByText("22km 150分 ≤150")).toBeInTheDocument();
    expect(screen.getAllByText("実施")).toHaveLength(2);
    // The week range comes from the plan week, and today is still marked.
    expect(screen.getByText("今週のプラン")).toBeInTheDocument();
    expect(screen.getByText("2026-09-07 〜 2026-09-13")).toBeInTheDocument();
    expect(screen.getByText("今日")).toBeInTheDocument();
    // Recommendations still come from the review.
    expect(screen.getByText("ロング走は時間×HRで管理")).toBeInTheDocument();
  });

  it("test_this_week_plan_falls_back_to_verdict_without_prescriptions", () => {
    const review = makeReview({
      verdict: [{ date: "2026-07-01", session: "Tempo", rating: "🟡" }],
    });

    renderPlan(review, new Date(2026, 6, 2), unprescribedWeek());

    expect(screen.getByText("Tempo")).toBeInTheDocument();
  });

  it("shows the CLI hint when no review exists", () => {
    renderPlan(null);

    expect(screen.getByText("週次レビューがまだありません")).toBeInTheDocument();
    expect(screen.getByText("/weekly-review")).toBeInTheDocument();
  });
});
