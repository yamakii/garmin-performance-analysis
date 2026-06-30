import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import ActivityDetail from "./ActivityDetail";
import type {
  ActivityDetailResponse,
  SectionsResponse,
  TrackPoint,
} from "../types";

const BASE_DETAIL: ActivityDetailResponse = {
  activity: {
    activity_id: 123,
    activity_date: "2025-10-09",
    activity_name: "Morning Run",
    total_distance_km: 5.66,
    total_time_seconds: 2186,
    avg_pace_seconds_per_km: 386,
    avg_heart_rate: 144,
  },
  splits: [
    {
      activity_id: 123,
      split_index: 1,
      distance: 1.0,
      duration_seconds: 386,
      pace_seconds_per_km: 386,
      heart_rate: 144,
      cadence: 168,
      power: 250,
    },
  ],
  form_efficiency: null,
  hr_zones: [],
  performance_trends: null,
  form_evaluations: null,
  vo2_max: null,
  lactate_threshold: null,
};

function stubFetch(opts: {
  detail: ActivityDetailResponse;
  sections: SectionsResponse;
  track: TrackPoint[];
}) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      let body: unknown;
      if (url.includes("/sections")) {
        body = opts.sections;
      } else if (url.includes("/time-series")) {
        body = { timestamps: [], metrics: {} };
      } else if (url.includes("/track")) {
        body = { points: opts.track };
      } else {
        body = opts.detail;
      }
      return Promise.resolve(
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }),
  );
}

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={["/activities/123"]}>
      <Routes>
        <Route path="/activities/:id" element={<ActivityDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ActivityDetail in-page nav", () => {
  it("omits コース from nav when track is absent", async () => {
    stubFetch({ detail: BASE_DETAIL, sections: {}, track: [] });
    renderDetail();

    const nav = await screen.findByRole("navigation", {
      name: "セクション目次",
    });
    expect(within(nav).queryByText("コース")).not.toBeInTheDocument();
  });

  it("includes スプリット in nav when splits exist", async () => {
    stubFetch({ detail: BASE_DETAIL, sections: {}, track: [] });
    renderDetail();

    const nav = await screen.findByRole("navigation", {
      name: "セクション目次",
    });
    const link = within(nav).getByRole("link", { name: "スプリット" });
    expect(link).toHaveAttribute("href", "#section-splits");

    // The corresponding splits section carries the matching anchor id.
    expect(document.getElementById("section-splits")).not.toBeNull();
  });
});
