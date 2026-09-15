import { useMemo } from "react";
import ChartHeader from "../../components/ChartHeader";
import EChart from "../../components/EChart";
import {
  AXIS_STYLE,
  BASELINE_BAND_COLOR,
  BASE_CHART_OPTION,
  INK_COLOR,
  METRIC_COLORS,
  THRESHOLD_LINE,
  X_AXIS_STYLE,
} from "../../components/chartTheme";
import { axisTooltipFormatter, formatNumber } from "../../utils/formatNumber";
import type { EChartsOption } from "../../lib/echarts";
import type {
  MetricBaseline,
  RecoveryTrend,
  WellnessBaselineDeviation,
} from "../../types";
import { HRV_STATUS_LABELS, RHR_TREND_LABELS } from "../../labels/recovery";

interface RecoveryPanelProps {
  data: RecoveryTrend;
  /** Personal baseline, drawn as the band each series is read against. */
  baseline?: WellnessBaselineDeviation | null;
}

const RHR_SERIES = "安静時心拍 (bpm)";
const HRV_SERIES = "夜間HRV (ms)";

/** Chart height: two stacked panels have to stay comparable at a glance. */
const PANEL_HEIGHT = 150;

/** The personal band of one metric (mean ± σ), or null when it has none. */
interface Band {
  lo: number;
  hi: number;
}

function bandOf(baseline: MetricBaseline | null | undefined): Band | null {
  if (baseline?.mean == null || baseline.std == null) {
    return null;
  }
  return { lo: baseline.mean - baseline.std, hi: baseline.mean + baseline.std };
}

/** "44–48" — the band as the chart header states it. */
function bandText(band: Band | null): string | null {
  return band == null
    ? null
    : `${formatNumber(band.lo, 0)}–${formatNumber(band.hi, 0)}`;
}

/**
 * Is this reading on the bad side of the band? RHR is judged above it and HRV
 * below it, so the same helper serves both by taking the adverse direction.
 */
function isAdverse(
  value: number | null,
  band: Band | null,
  adverse: "above" | "below",
): boolean {
  if (value == null || band == null) {
    return false;
  }
  return adverse === "above" ? value > band.hi : value < band.lo;
}

/**
 * One metric's panel: the line, the baseline band behind it, and the adverse
 * points repainted in the 注意 hue so an out-of-band night is visible without
 * reading the axis.
 */
function panelOption(
  name: string,
  unit: string,
  color: string,
  values: (number | null)[],
  dates: string[],
  band: Band | null,
  adverse: "above" | "below",
): EChartsOption {
  return {
    ...BASE_CHART_OPTION,
    grid: { left: 48, right: 12, top: 24, bottom: 24 },
    tooltip: {
      trigger: "axis" as const,
      formatter: axisTooltipFormatter({ [name]: 0 }),
    },
    xAxis: { type: "category" as const, data: dates, ...X_AXIS_STYLE },
    yAxis: {
      type: "value" as const,
      name: unit,
      nameTextStyle: { color },
      scale: true,
      ...AXIS_STYLE,
    },
    series: [
      {
        name,
        type: "line" as const,
        smooth: true,
        connectNulls: false,
        symbolSize: 5,
        itemStyle: { color },
        lineStyle: { color },
        data: values.map((value) =>
          isAdverse(value, band, adverse)
            ? { value, itemStyle: { color: THRESHOLD_LINE.warn } }
            : value,
        ),
        // The band is the reading's context: inside it the night was ordinary.
        markArea:
          band == null
            ? undefined
            : {
                silent: true,
                data: [
                  [
                    { yAxis: band.lo, itemStyle: { color: BASELINE_BAND_COLOR } },
                    { yAxis: band.hi },
                  ],
                ],
              },
      },
    ],
  };
}

/**
 * 回復トレンド: resting heart rate and overnight HRV, one single-axis panel
 * each.
 *
 * The two metrics are read in opposite directions (low RHR = good, high HRV =
 * good), so overlaying them on a dual axis made every crossing meaningless
 * (#691). Each panel now carries its own `ChartHeader` instead of a legend:
 * a single series needs no colour key, it needs to know what band it is being
 * judged against and whether it is currently outside it.
 */
export default function RecoveryPanel({ data, baseline }: RecoveryPanelProps) {
  const { rhr, hrv, series } = data;

  // Memoised so the chart options keep their identity across renders: EChart
  // re-initialises whenever `option` changes.
  const rhrBand = useMemo(() => bandOf(baseline?.rhr), [baseline?.rhr]);
  const hrvBand = useMemo(() => bandOf(baseline?.hrv), [baseline?.hrv]);

  const dates = useMemo(() => series.map((point) => point.date), [series]);

  const rhrOption = useMemo(
    () =>
      panelOption(
        RHR_SERIES,
        "bpm",
        // Single-series charts draw their primary in ink (chartTheme). RHR
        // used to take METRIC_COLORS.heart_rate, and the 注意 dots marking an
        // out-of-band night were nearly invisible on that red line (#1189).
        INK_COLOR,
        series.map((point) => point.resting_hr),
        dates,
        rhrBand,
        "above",
      ),
    [dates, series, rhrBand],
  );

  const hrvOption = useMemo(
    () =>
      panelOption(
        HRV_SERIES,
        "ms",
        METRIC_COLORS.hrv,
        series.map((point) => point.hrv_overnight_ms),
        dates,
        hrvBand,
        "below",
      ),
    [dates, series, hrvBand],
  );

  const rhrOutside = series.filter((point) =>
    isAdverse(point.resting_hr, rhrBand, "above"),
  ).length;
  const hrvOutside = series.filter((point) =>
    isAdverse(point.hrv_overnight_ms, hrvBand, "below"),
  ).length;

  const window = `${data.weeks}週`;

  if (series.length === 0) {
    return (
      <p className="text-[15px] leading-[1.7] text-ink-muted">
        回復データ (RHR / HRV) の記録がありません
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <ChartHeader
          title="安静時心拍"
          note={[window, bandText(rhrBand) && `基準帯 ${bandText(rhrBand)}bpm`]
            .filter(Boolean)
            .join(" · ")}
          status={
            rhrOutside > 0
              ? `${rhrOutside}日 基準超`
              : rhr.rhr_trend != null
                ? RHR_TREND_LABELS[rhr.rhr_trend]
                : undefined
          }
          statusTone={rhrOutside > 0 ? "warn" : "muted"}
        />
        <EChart
          option={rhrOption}
          ariaLabel="安静時心拍の推移グラフ"
          height={PANEL_HEIGHT}
        />
      </div>
      <div className="flex flex-col gap-1">
        <ChartHeader
          title="夜間HRV"
          note={[window, bandText(hrvBand) && `基準帯 ${bandText(hrvBand)}ms`]
            .filter(Boolean)
            .join(" · ")}
          status={
            hrvOutside > 0
              ? `${hrvOutside}日 基準割れ`
              : hrv.status != null
                ? HRV_STATUS_LABELS[hrv.status]
                : undefined
          }
          statusTone={hrvOutside > 0 || hrv.under_recovery ? "warn" : "muted"}
        />
        <EChart
          option={hrvOption}
          ariaLabel="夜間HRVの推移グラフ"
          height={PANEL_HEIGHT}
        />
      </div>
    </div>
  );
}
