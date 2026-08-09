import type { ReactElement } from "react";
import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import BodyCompositionChart from "./BodyCompositionChart";
import DurabilityBlock from "./DurabilityBlock";
import HeatAdjustedBlock from "./HeatAdjustedBlock";
import ObjectiveFitnessBlock from "./ObjectiveFitnessBlock";
import PhysiologyBlock from "./PhysiologyBlock";
import RecoveryPanel from "./RecoveryPanel";
import TrainingLoadBlock from "./TrainingLoadBlock";
import WeightEconomyChart from "./WeightEconomyChart";
import type {
  HeatAdjustedTrend,
  ObjectiveFitnessTrend,
  PhysiologyTrend,
} from "../../api/trends";
import type {
  AcwrTrend,
  BodyCompositionTrend,
  DurabilityTrend,
  RecoveryTrend,
  WeightEconomyCoupling,
} from "../../types";

// EChart is replaced by a collector: these are option-semantics tests, so what
// matters is the option each block hands to the renderer, not the canvas.
const captured = vi.hoisted(() => ({ options: [] as ChartOption[] }));

vi.mock("../../components/EChart", () => ({
  default: (props: { option: unknown }) => {
    captured.options.push(props.option as ChartOption);
    return null;
  },
}));

type ColorStyle = { color?: string };
type MarkPoint = { yAxis?: number };
type Series = {
  name?: string;
  itemStyle?: ColorStyle;
  lineStyle?: ColorStyle;
  markArea?: { data?: MarkPoint[][] };
  markLine?: { data?: MarkPoint[] };
};
type Axis = { name?: string; nameTextStyle?: ColorStyle };
type ChartOption = {
  tooltip?: { formatter?: unknown };
  yAxis?: Axis | Axis[];
  series?: Series[];
};

/** Render a block and return the options it fed to EChart, in render order. */
function optionsOf(ui: ReactElement): ChartOption[] {
  captured.options.length = 0;
  render(ui);
  return [...captured.options];
}

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
      { week_start: "2026-06-29", load_km: 30.1, acwr: 1.12, status: "optimal" },
    ],
    load_metric: "distance_km",
  },
};

const PHYSIOLOGY: PhysiologyTrend = {
  vo2max: [
    { date: "2026-06-01", value: 52.1 },
    { date: "2026-07-01", value: 52.6 },
  ],
  lactate_threshold: [{ date: "2026-06-01", heart_rate: 168, speed_mps: 3.5 }],
};

const OBJECTIVE: ObjectiveFitnessTrend = {
  objective_curve: [
    { date: "2026-06-01", vdot: 47.2, source_distance_km: 10 },
  ],
  garmin_vo2max: [{ date: "2026-06-01", value: 52 }],
  optimism_gap: null,
};

const RECOVERY: RecoveryTrend = {
  weeks: 8,
  rhr: { median_7d: 45, median_30d: 46, rhr_trend: "stable" },
  hrv: {
    latest_ms: 51,
    status: "balanced",
    hrv_below_baseline_days: 0,
    under_recovery: false,
  },
  series: [
    { date: "2026-06-30", resting_hr: 45, hrv_overnight_ms: 47 },
    { date: "2026-07-01", resting_hr: 46, hrv_overnight_ms: 51 },
  ],
};

const WEIGHT_ECONOMY: WeightEconomyCoupling = {
  weeks: 52,
  n_matched: 2,
  weight_spread_kg: 1.2,
  model: null,
  series: [
    {
      activity_id: 1,
      run_date: "2026-06-01",
      weight_kg: 78.2,
      ef: 0.0176,
      weight_gap_days: 0,
    },
    {
      activity_id: 2,
      run_date: "2026-06-15",
      weight_kg: 77.4,
      ef: 0.0181,
      weight_gap_days: 1,
    },
  ],
  note: "",
};

const HEAT: HeatAdjustedTrend = {
  status: "ok",
  coefficients: { beta_heat: 0.35, ref_temp_c: 15, n: 12 },
  neutral_hr_slope: -0.02,
  points: [
    {
      date: "2026-07-01",
      temp_c: 28,
      raw_hr: 150,
      heat_cost: 4.55,
      neutral_hr: 145.45,
    },
  ],
};

const BODY: BodyCompositionTrend = {
  weeks: 12,
  series: [
    { date: "2026-06-01", weight_kg: 78.2, fat_mass: 14.1, lean_mass: 64.1 },
  ],
  change: {
    delta_weight: -1.2,
    delta_fat: -1,
    delta_lean: -0.2,
    lean_loss_ratio: 0.17,
    muscle_loss_warning: false,
  },
  lean_pwr: null,
};

const DURABILITY: DurabilityTrend = {
  activities: [
    {
      activity_id: 1,
      activity_date: "2026-06-01",
      distance_km: 15.2,
      decoupling_pct: 3.1,
      pace_fade_pct: 1.2,
      gct_fade_pct: 2,
      vo_fade_pct: 1.1,
      vr_fade_pct: 0.4,
    },
  ],
  trend: {
    decoupling_slope_per_day: 0.01,
    data_points: 5,
    direction: "stable",
    gct_fade_slope_per_day: null,
    form_direction: "stable",
  },
};

describe("TrainingLoadBlock", () => {
  it("test_acwr_optimal_band_present", () => {
    const [option] = optionsOf(<TrainingLoadBlock data={LOAD} />);
    const acwr = option.series?.find((s) => s.name === "ACWR");

    // 0.8-1.3 shaded band: the line now has a target to be read against.
    const band = acwr?.markArea?.data?.[0];
    expect(band?.[0].yAxis).toBe(0.8);
    expect(band?.[1].yAxis).toBe(1.3);
    // Faint lower bound at 0.8, and the 1.5 high-risk line is kept.
    expect(acwr?.markLine?.data?.map((d) => d.yAxis)).toEqual([0.8, 1.5]);
  });
});

describe("VO2max color", () => {
  it("test_vo2max_color_consistent", () => {
    const [physiology] = optionsOf(<PhysiologyBlock data={PHYSIOLOGY} />);
    const [objective] = optionsOf(<ObjectiveFitnessBlock data={OBJECTIVE} />);

    const physiologyVo2max = physiology.series?.find(
      (s) => s.name === "VO2max",
    );
    const garminVo2max = objective.series?.find(
      (s) => s.name === "Garmin VO2max",
    );
    const objectiveVdot = objective.series?.find((s) => s.name === "客観VDOT");

    // One metric, one color across the two pages that plot it.
    expect(physiologyVo2max?.lineStyle?.color).toBe(
      garminVo2max?.lineStyle?.color,
    );
    expect(physiologyVo2max?.itemStyle?.color).toBe(
      garminVo2max?.itemStyle?.color,
    );
    // Its comparison partner owns a different token (no borrowing).
    expect(objectiveVdot?.lineStyle?.color).not.toBe(
      garminVo2max?.lineStyle?.color,
    );
  });
});

describe("RecoveryPanel", () => {
  it("test_recovery_panel_two_charts", () => {
    const options = optionsOf(<RecoveryPanel data={RECOVERY} />);

    // RHR (low = good) and HRV (high = good) no longer share a dual axis.
    expect(options).toHaveLength(2);
    for (const option of options) {
      expect(Array.isArray(option.yAxis)).toBe(false);
      expect(option.series).toHaveLength(1);
    }
  });
});

describe("dual-axis charts", () => {
  it("test_dual_axis_name_colors_match_series", () => {
    const [option] = optionsOf(<PhysiologyBlock data={PHYSIOLOGY} />);
    const axes = option.yAxis as Axis[];
    const series = option.series ?? [];

    expect(axes).toHaveLength(2);
    axes.forEach((axis, index) => {
      expect(axis.nameTextStyle?.color).toBe(series[index].lineStyle?.color);
    });
  });
});

describe("tooltips", () => {
  it("test_tooltip_formatter_applied", () => {
    const charts: ReactElement[] = [
      <WeightEconomyChart data={WEIGHT_ECONOMY} />,
      <HeatAdjustedBlock data={HEAT} />,
      <RecoveryPanel data={RECOVERY} />,
      <ObjectiveFitnessBlock data={OBJECTIVE} />,
      <BodyCompositionChart data={BODY} />,
    ];

    for (const chart of charts) {
      const options = optionsOf(chart);
      expect(options.length).toBeGreaterThan(0);
      for (const option of options) {
        expect(typeof option.tooltip?.formatter).toBe("function");
      }
    }
  });
});

describe("DurabilityBlock", () => {
  it("test_durability_single_warning_line", () => {
    const [option] = optionsOf(<DurabilityBlock data={DURABILITY} />);

    // Both series share the 5% threshold: one line, drawn once.
    const lines = (option.series ?? []).flatMap((s) => s.markLine?.data ?? []);
    expect(lines).toHaveLength(1);
    expect(lines[0].yAxis).toBe(5);

    const formatter = option.tooltip?.formatter as (p: unknown) => string;
    const html = formatter([{ axisValue: "2026-06-01" }]);
    expect(html).toContain("デカップリング");
    expect(html).toContain("GCT後半失速");
    // VO / VR fades are not plotted here, so the tooltip must not list them.
    expect(html).not.toContain("上下動");
  });
});
