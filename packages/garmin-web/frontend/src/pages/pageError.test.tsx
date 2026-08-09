import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "../test/utils";
import ActivityDetail from "./ActivityDetail";
import ActivityList from "./ActivityList";
import Goal from "./Goal";
import WeeklyReviewDetail from "./WeeklyReviewDetail";
import WeeklyReviews from "./WeeklyReviews";

/**
 * Cross-page contract for a failed page-level fetch (Issue #914).
 *
 * Every route used to word its own banner (`エラー: {message}`) and offer no
 * way out but a browser reload. The audit in #910 counted five variants of the
 * same state, so the wording and the retry affordance are asserted here once,
 * across all five pages, instead of drifting apart again.
 */

// echarts requires a real canvas; mock the modular wrapper out for jsdom.
vi.mock("../lib/echarts", () => ({
  echarts: {
    init: () => ({
      setOption: vi.fn(),
      resize: vi.fn(),
      dispose: vi.fn(),
      dispatchAction: vi.fn(),
      on: vi.fn(),
      getZr: () => ({ on: vi.fn() }),
    }),
  },
}));

afterEach(() => {
  vi.unstubAllGlobals();
});

/** Every API call fails, so each page lands in its fatal-error branch. */
function stubFailingApi(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "db down" }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );
}

const PAGES: [string, () => ReactElement][] = [
  [
    "ActivityList",
    () => (
      <MemoryRouter initialEntries={["/activities"]}>
        <ActivityList />
      </MemoryRouter>
    ),
  ],
  [
    "ActivityDetail",
    () => (
      <MemoryRouter initialEntries={["/activities/123"]}>
        <Routes>
          <Route path="/activities/:id" element={<ActivityDetail />} />
        </Routes>
      </MemoryRouter>
    ),
  ],
  [
    "Goal",
    () => (
      <MemoryRouter initialEntries={["/goal"]}>
        <Goal />
      </MemoryRouter>
    ),
  ],
  [
    "WeeklyReviews",
    () => (
      <MemoryRouter initialEntries={["/weekly-reviews"]}>
        <WeeklyReviews />
      </MemoryRouter>
    ),
  ],
  [
    "WeeklyReviewDetail",
    () => (
      <MemoryRouter initialEntries={["/weekly-reviews/2026-06-15"]}>
        <Routes>
          <Route
            path="/weekly-reviews/:weekStart"
            element={<WeeklyReviewDetail />}
          />
        </Routes>
      </MemoryRouter>
    ),
  ],
];

describe("page-level error state", () => {
  it("test_error_wording_unified", async () => {
    for (const [name, renderPage] of PAGES) {
      stubFailingApi();
      const { unmount } = render(renderPage());

      const alert = await screen.findByRole("alert");
      expect(alert.textContent, name).toContain("読み込みに失敗しました");
      // The old per-page wording — a bare "エラー:" prefix with no recovery.
      expect(alert.textContent, name).not.toContain("エラー:");
      expect(
        within(alert).getByRole("button", { name: "再試行" }),
        name,
      ).toBeInTheDocument();

      unmount();
    }
  });
});
