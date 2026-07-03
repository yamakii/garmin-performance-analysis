import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "../test/utils";
import WeeklyReviews from "./WeeklyReviews";

const FIXTURE_REVIEWS = [
  {
    review_id: 2,
    user_id: "default",
    week_start_date: "2026-06-15",
    week_end_date: "2026-06-21",
    review_date: "2026-06-22",
    review_data: {
      this_week: { volume_km: 35.5, run_count: 4 },
      verdict: [
        { date: "2026-06-20", session: "Anaerobic", rating: "🔴", comment: "x" },
        { date: "2026-06-21", session: "Anaerobic", rating: "🔴", comment: "y" },
      ],
      overall: "2週目は強度過多に注意が必要でした。",
    },
    created_at: null,
    agent_name: "weekly-review",
    agent_version: "1.0",
  },
  {
    review_id: 1,
    user_id: "default",
    week_start_date: "2026-06-08",
    week_end_date: "2026-06-14",
    review_date: "2026-06-15",
    review_data: {
      this_week: { volume_km: 28.8, run_count: 3 },
      verdict: [
        { date: "2026-06-09", session: "Easy", rating: "✅", comment: "ok" },
      ],
      overall: "1週目は順調に積み上げられました。",
    },
    created_at: null,
    agent_name: "weekly-review",
    agent_version: "1.0",
  },
];

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("WeeklyReviews", () => {
  it("WeeklyReviews still shows 週次レビュー heading", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(FIXTURE_REVIEWS), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    render(
      <MemoryRouter>
        <WeeklyReviews />
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole("heading", { level: 1, name: "週次レビュー" }),
    ).toBeInTheDocument();
  });

  it("renders the weekly review list from API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(FIXTURE_REVIEWS), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    render(
      <MemoryRouter>
        <WeeklyReviews />
      </MemoryRouter>,
    );

    // Week range labels (newest first)
    expect(
      await screen.findByText("2026-06-15 〜 2026-06-21"),
    ).toBeInTheDocument();
    expect(screen.getByText("2026-06-08 〜 2026-06-14")).toBeInTheDocument();

    // Overall excerpts rendered
    expect(
      screen.getByText("2週目は強度過多に注意が必要でした。"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("1週目は順調に積み上げられました。"),
    ).toBeInTheDocument();

    // Each row links to its detail page
    const links = screen.getAllByRole("link");
    const hrefs = links.map((l) => l.getAttribute("href"));
    expect(hrefs).toContain("/weekly-reviews/2026-06-15");
    expect(hrefs).toContain("/weekly-reviews/2026-06-08");
  });

  it("shows a /weekly-review CLI hint when there are no reviews", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    render(
      <MemoryRouter>
        <WeeklyReviews />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("週次レビューが登録されていません"),
    ).toBeInTheDocument();
    expect(screen.getByText("/weekly-review")).toBeInTheDocument();
  });
});
