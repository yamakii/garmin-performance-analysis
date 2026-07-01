import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { WeeklyReview } from "../../types";
import ThisWeekPlan, { toIsoDate } from "./ThisWeekPlan";

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

function renderPlan(review: WeeklyReview | null, today?: Date) {
  return render(
    <MemoryRouter>
      <ThisWeekPlan review={review} today={today} />
    </MemoryRouter>,
  );
}

describe("toIsoDate", () => {
  it("formats a local date without UTC shift", () => {
    expect(toIsoDate(new Date(2026, 6, 2))).toBe("2026-07-02");
    expect(toIsoDate(new Date(2026, 0, 5))).toBe("2026-01-05");
  });
});

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

  it("shows the CLI hint when no review exists", () => {
    renderPlan(null);

    expect(screen.getByText("週次レビューがまだありません")).toBeInTheDocument();
    expect(screen.getByText("/weekly-review")).toBeInTheDocument();
  });
});
