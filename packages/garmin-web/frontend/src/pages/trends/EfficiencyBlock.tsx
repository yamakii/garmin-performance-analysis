import { useMemo } from "react";
import EChart from "../../components/EChart";
import {
  AXIS_STYLE,
  BASE_CHART_OPTION,
  X_AXIS_STYLE,
  ZONE_COLORS,
} from "../../components/chartTheme";
import { axisTooltipFormatter } from "../../utils/formatNumber";
import type { EfficiencyTrendPoint } from "../../api/trends";
import { BLOCK_SUMMARY_CLASS, BlockEmpty, CHART_HEIGHT } from "./blockShell";

interface EfficiencyBlockProps {
  data: EfficiencyTrendPoint[];
}

const ZONE_KEYS = [
  "zone1_percentage",
  "zone2_percentage",
  "zone3_percentage",
  "zone4_percentage",
  "zone5_percentage",
] as const;

/** The five zone shares of one run, missing values read as zero. */
function zoneShares(point: EfficiencyTrendPoint): number[] {
  return ZONE_KEYS.map((key) => point[key] ?? 0);
}

/**
 * "最新 2025-10-06 · 主ゾーン Zone 2 · 低強度 70%" — where the latest run sat.
 *
 * Low intensity (zones 1-2) is the number an easy-run week is judged by, so it
 * is stated outright instead of leaving the reader to add the two bars up.
 */
export function efficiencySummaryLine(data: EfficiencyTrendPoint[]): string {
  const latest = data[data.length - 1] ?? null;
  if (latest == null) {
    return "";
  }
  const shares = zoneShares(latest);
  const easy = shares[0] + shares[1];
  const parts = [`最新 ${latest.date}`];
  if (latest.primary_zone != null) {
    parts.push(`主ゾーン ${latest.primary_zone}`);
  }
  parts.push(`低強度 ${easy.toFixed(0)}%`);
  return parts.join(" · ");
}

/** The latest run's zone split as bars — the chart's history in one column. */
function ZoneBars({ point }: { point: EfficiencyTrendPoint }) {
  const shares = zoneShares(point);
  return (
    <ul aria-label="HRゾーン分布" className="flex flex-col gap-1.5">
      {shares.map((share, index) => (
        <li
          // The five zones are a fixed, ordered set: the index is the identity.
          // eslint-disable-next-line react/no-array-index-key
          key={index}
          className="grid grid-cols-[28px_1fr_40px] items-center gap-2"
        >
          <span className="font-mono text-xs text-ink-muted">Z{index + 1}</span>
          <span className="block h-2 bg-well">
            <span
              data-zone={index + 1}
              className="block h-2"
              style={{
                width: `${Math.max(0, Math.min(100, share))}%`,
                backgroundColor: ZONE_COLORS[index],
              }}
            />
          </span>
          <span className="text-right font-mono text-xs text-ink">
            {share.toFixed(0)}%
          </span>
        </li>
      ))}
    </ul>
  );
}

export default function EfficiencyBlock({ data }: EfficiencyBlockProps) {
  const option = useMemo(
    () => ({
      ...BASE_CHART_OPTION,
      tooltip: {
        trigger: "axis" as const,
        formatter: axisTooltipFormatter({}),
      },
      xAxis: {
        type: "category" as const,
        data: data.map((p) => p.date),
        ...X_AXIS_STYLE,
      },
      yAxis: { type: "value" as const, name: "%", max: 100, ...AXIS_STYLE },
      series: ZONE_KEYS.map((key, i) => ({
        name: `Zone ${i + 1}`,
        type: "bar" as const,
        stack: "zones",
        // Square bars, and the zone ramp instead of a legend: the bars beside
        // the chart name the zones (§Charts).
        itemStyle: { color: ZONE_COLORS[i], borderRadius: 0 },
        data: data.map((p) => p[key]),
      })),
    }),
    [data],
  );

  const latest = data[data.length - 1] ?? null;
  if (latest == null) {
    return <BlockEmpty message="データがありません" />;
  }
  return (
    <div className="grid gap-6 md:grid-cols-[2fr_1fr]">
      <div className="flex flex-col gap-3">
        <p className={BLOCK_SUMMARY_CLASS}>{efficiencySummaryLine(data)}</p>
        <EChart
          option={option}
          ariaLabel="HRゾーン分布の積み上げ棒グラフ"
          height={CHART_HEIGHT}
        />
      </div>
      <ZoneBars point={latest} />
    </div>
  );
}
