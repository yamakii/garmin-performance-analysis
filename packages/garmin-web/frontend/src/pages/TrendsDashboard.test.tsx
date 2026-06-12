import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import TrendsDashboard from "./TrendsDashboard";

// echarts requires a real canvas; mock it out for jsdom
vi.mock("echarts", () => ({
  init: () => ({
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
  }),
}));

const VOLUME = [
  { bucket: "2025-W41", distance_km: 15.0, duration_seconds: 5400, run_count: 2 },
  { bucket: "2025-W42", distance_km: 8.0, duration_seconds: 2400, run_count: 1 },
];

const PHYSIOLOGY = {
  vo2max: [
    { date: "2025-10-06", value: 49.6 },
    { date: "2025-10-13", value: 50.1 },
  ],
  lactate_threshold: [{ date: "2025-10-13", heart_rate: 168, speed_mps: 3.2 }],
};

const FORM = [
  {
    date: "2025-10-06",
    overall_score: 4.2,
    gct_delta: 2.5,
    vo_delta: 0.4,
    vr_delta: 0.3,
  },
];

const EFFICIENCY = [
  {
    date: "2025-10-06",
    aerobic_efficiency: "good",
    primary_zone: "Zone 2",
    zone1_percentage: 10.0,
    zone2_percentage: 60.0,
    zone3_percentage: 20.0,
    zone4_percentage: 8.0,
    zone5_percentage: 2.0,
  },
];

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("TrendsDashboard", () => {
  it("renders all four trend blocks from API data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        if (url.startsWith("/api/trends/volume")) {
          return Promise.resolve(jsonResponse(VOLUME));
        }
        if (url.startsWith("/api/trends/physiology")) {
          return Promise.resolve(jsonResponse(PHYSIOLOGY));
        }
        if (url.startsWith("/api/trends/form")) {
          return Promise.resolve(jsonResponse(FORM));
        }
        if (url.startsWith("/api/trends/efficiency")) {
          return Promise.resolve(jsonResponse(EFFICIENCY));
        }
        return Promise.reject(new Error(`Unexpected fetch: ${url}`));
      }),
    );

    render(<TrendsDashboard />);

    // All four block headings appear once data is loaded
    expect(
      await screen.findByRole("heading", { level: 2, name: "走行量" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: "生理指標 (VO2max / 乳酸閾値)" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: "フォームスコア推移" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: "効率推移 (HRゾーン分布)" }),
    ).toBeInTheDocument();

    // Volume block summary is rendered from the mocked API data
    expect(screen.getByText(/2025-W42/)).toBeInTheDocument();
    expect(screen.getByText(/8\.0 km/)).toBeInTheDocument();

    // Physiology block shows the latest VO2max from the mocked API data
    expect(screen.getByText(/最新VO2max: 50\.1/)).toBeInTheDocument();
  });
});
