import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type {
  AcwrTrend,
  FormAnomalyFlagsResponse,
  RecoveryTrend,
} from "../../types";
import SnapshotTiles from "./SnapshotTiles";

// echarts requires a real canvas; mock the modular wrapper out for jsdom.
vi.mock("../../lib/echarts", () => ({
  echarts: {
    init: () => ({
      setOption: vi.fn(),
      resize: vi.fn(),
      dispose: vi.fn(),
    }),
  },
}));

const LOAD: AcwrTrend = {
  current: {
    end_date: "2026-07-01",
    acute_load_7d: 26.4,
    chronic_load_28d_weekly: 25.9,
    acwr: 1.02,
    status: "optimal",
    load_metric: "distance_km",
  },
  trend: {
    weeks: [
      { week_start: "2026-06-22", load_km: 26.4, acwr: 0.99, status: "optimal" },
      { week_start: "2026-06-29", load_km: 6.5, acwr: 1.02, status: "optimal" },
    ],
    load_metric: "distance_km",
  },
};

const RECOVERY: RecoveryTrend = {
  weeks: 8,
  rhr: { median_7d: 45, median_30d: 45, rhr_trend: "stable" },
  hrv: {
    latest_ms: 51,
    status: "low",
    hrv_below_baseline_days: 2,
    under_recovery: true,
  },
  series: [
    { date: "2026-06-30", resting_hr: 45, hrv_overnight_ms: 47 },
    { date: "2026-07-01", resting_hr: 48, hrv_overnight_ms: 51 },
  ],
};

const FLAGS: FormAnomalyFlagsResponse = {
  weeks: 2,
  scanned: 6,
  limited: false,
  flags: [
    {
      activity_id: 1,
      activity_date: "2026-06-28",
      anomalies_detected: 2,
      severity_high: 1,
      top_recommendation: "接地時間の左右差に注意",
    },
  ],
};

function renderTiles(
  load: AcwrTrend | null = LOAD,
  recovery: RecoveryTrend | null = RECOVERY,
  flags: FormAnomalyFlagsResponse | null = FLAGS,
) {
  return render(
    <MemoryRouter>
      <SnapshotTiles load={load} recovery={recovery} flags={flags} />
    </MemoryRouter>,
  );
}

describe("SnapshotTiles", () => {
  it("renders the ACWR value with its status badge", () => {
    renderTiles();

    expect(screen.getByText("1.02")).toBeInTheDocument();
    expect(screen.getByText("最適")).toBeInTheDocument();
  });

  it("renders HRV with the under-recovery badge and RHR with its trend", () => {
    renderTiles();

    expect(screen.getByText("51")).toBeInTheDocument();
    expect(screen.getByText("回復不足")).toBeInTheDocument();
    expect(screen.getByText("45")).toBeInTheDocument();
    expect(screen.getByText("安定")).toBeInTheDocument();
    expect(screen.getByText("基準割れ 2日連続")).toBeInTheDocument();
  });

  it("renders the form-anomaly count and top recommendation", () => {
    renderTiles();

    expect(screen.getByText("1件")).toBeInTheDocument();
    expect(screen.getByText("接地時間の左右差に注意")).toBeInTheDocument();
  });

  it("shows 問題なし when no flags are raised", () => {
    renderTiles(LOAD, RECOVERY, { ...FLAGS, flags: [] });

    expect(screen.getByText("問題なし")).toBeInTheDocument();
    expect(screen.getByText("直近2週のランに異常なし")).toBeInTheDocument();
  });

  it("falls back to dashes when data is missing", () => {
    renderTiles(null, null, null);

    // All four tiles render a placeholder value instead of crashing.
    expect(screen.getAllByText("—")).toHaveLength(4);
  });

  it("タイルが該当ページへリンクする", () => {
    renderTiles();

    // Each tile deep-links to its matching Trends anchor.
    const recoveryTile = screen.getByText("HRV (夜間)").closest("a");
    expect(recoveryTile).toHaveAttribute("href", "/trends#recovery");

    const rhrTile = screen.getByText("安静時心拍").closest("a");
    expect(rhrTile).toHaveAttribute("href", "/trends#recovery");

    const loadTile = screen.getByText("訓練負荷 (ACWR)").closest("a");
    expect(loadTile).toHaveAttribute("href", "/trends#training-load");

    const flagsTile = screen.getByText("フォーム注意点").closest("a");
    expect(flagsTile).toHaveAttribute("href", "/trends#form-anomaly");
  });

  it("shows a dash for ACWR when data is insufficient", () => {
    renderTiles({
      current: {
        end_date: null,
        acute_load_7d: 0,
        chronic_load_28d_weekly: 0,
        acwr: null,
        status: "insufficient_data",
        load_metric: "distance_km",
      },
      trend: { weeks: [], load_metric: "distance_km" },
    });

    expect(screen.getByText("データ不足")).toBeInTheDocument();
  });
});
