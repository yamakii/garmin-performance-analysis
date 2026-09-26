import { useMemo } from "react";
import type { TopLevelFormatterParams } from "echarts/types/dist/shared";
import ChartHeader from "../../components/ChartHeader";
import EChart from "../../components/EChart";
import {
  AXIS_STYLE,
  BASELINE_BAND_COLOR,
  BASE_CHART_OPTION,
  CHART_FONT_FAMILY,
  CHART_FONT_SIZE,
  CHART_GRID,
  CHART_SPLIT_NUMBER,
  COMPARE_COLOR,
  INK_COLOR,
  THRESHOLD_LINE,
  X_AXIS_STYLE,
} from "../../components/chartTheme";
import type { EChartsOption } from "../../lib/echarts";
import { formatDateLabel } from "../../utils/format";
import { formatNumber, formatSigned } from "../../utils/formatNumber";
import type { EnergyBalance, EnergyBalanceDay } from "../../types";
import {
  bandNote,
  calibrationText,
  headerStatus,
  monthDay,
  reasonLabel,
} from "./energyBalanceLabels";

/** Same height as the 体組成 chart right below it (Morning Brief §7). */
const CHART_HEIGHT = 160;

/** Tooltip for one day: the numbers of a used day, the reason of an excluded one. */
function dayTooltip(day: EnergyBalanceDay, reason: string | undefined): string {
  const date = formatDateLabel(day.date);
  if (!day.used) {
    return `${date} · ${reasonLabel(reason ?? day.intake_status)}`;
  }
  const provisional = day.intake_status === "provisional" ? " · 暫定" : "";
  return (
    `${date} · 摂取 ${formatNumber(day.intake_kcal, 0)} / ` +
    `消費 ${formatNumber(day.expenditure_kcal, 0)} · ` +
    `収支 ${formatSigned(day.balance_kcal, 0)}${provisional}`
  );
}

/**
 * The daily bar strip (Issue #1439). One ink bar per window day; a day left out
 * of the mean has no bar (null, never 0) and names its reason under the date.
 * The block's target band is the baseline-band shade and the window mean a
 * dotted line, in the warn colour only when the mean left the band.
 */
export function buildEnergyBalanceOption(data: EnergyBalance): EChartsOption {
  const days = data.days.filter((day) => day.in_window);
  const reasons = new Map(
    data.window.excluded.map((entry) => [entry.date, entry.reason]),
  );
  const band = data.target.band_kcal;
  const mean =
    data.window.status === "ok" ? data.window.mean_balance_kcal : null;
  const offTarget =
    data.target.verdict === "deeper_than_target" ||
    data.target.verdict === "shallower_than_target";

  return {
    ...BASE_CHART_OPTION,
    grid: { ...CHART_GRID },
    tooltip: {
      trigger: "axis",
      formatter: (params: TopLevelFormatterParams) => {
        const list = Array.isArray(params) ? params : [params];
        const index = (list[0] as { dataIndex?: number })?.dataIndex;
        const day = index != null ? days[index] : undefined;
        return day != null ? dayTooltip(day, reasons.get(day.date)) : "";
      },
    },
    xAxis: {
      type: "category",
      data: days.map((day) => day.date),
      ...X_AXIS_STYLE,
      axisLabel: {
        ...X_AXIS_STYLE.axisLabel,
        interval: 0,
        formatter: (value: string) => {
          const reason = reasons.get(value);
          return reason != null
            ? `${monthDay(value)}\n${reasonLabel(reason)}`
            : monthDay(value);
        },
      },
    },
    yAxis: {
      type: "value",
      name: "kcal",
      splitNumber: CHART_SPLIT_NUMBER,
      // Keep the band and zero on the axis even when every bar sits outside.
      min: (extent: { min: number }) =>
        Math.min(extent.min, band?.[0] ?? 0, 0),
      max: (extent: { max: number }) =>
        Math.max(extent.max, band?.[1] ?? 0, 0),
      ...AXIS_STYLE,
    },
    series: [
      {
        name: "収支",
        type: "bar",
        data: days.map((day) => (day.used ? day.balance_kcal : null)),
        barMaxWidth: 28,
        itemStyle: { color: INK_COLOR, borderRadius: 0 },
        ...(band != null && {
          markArea: {
            silent: true,
            itemStyle: { color: BASELINE_BAND_COLOR },
            data: [[{ yAxis: band[0] }, { yAxis: band[1] }]],
          },
        }),
        ...(mean != null && {
          markLine: {
            silent: true,
            symbol: "none",
            lineStyle: {
              color: offTarget ? THRESHOLD_LINE.warn : COMPARE_COLOR,
              type: "dotted",
            },
            label: {
              formatter: "平均",
              fontFamily: CHART_FONT_FAMILY,
              fontSize: CHART_FONT_SIZE,
              color: offTarget ? THRESHOLD_LINE.warn : COMPARE_COLOR,
            },
            data: [{ yAxis: mean }],
          },
        }),
      },
    ],
  };
}

/** One reading of the window (the 体組成 `Reading` style, without a swatch). */
function Reading({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div>
      <dt className="font-mono text-xs text-ink-muted">{label}</dt>
      <dd className="mt-1 font-mono text-[20px] leading-none font-medium text-ink">
        {value}
        <span className="ml-[3px] font-sans text-[13px] text-ink-muted">
          kcal/日
        </span>
      </dd>
      {sub != null && (
        <dd className="mt-1.5 font-mono text-xs text-ink-muted">{sub}</dd>
      )}
    </div>
  );
}

/**
 * エネルギー収支 on /condition (Issue #1439): the window readings, a header
 * stating the verdict against the block's target band, and the daily strip.
 * A window too thin to judge keeps the strip — which days are missing, and why,
 * is the useful part then — but drops the readings, which would be a mean of
 * whatever days happened to be logged.
 */
export default function EnergyBalancePanel({ data }: { data: EnergyBalance }) {
  const option = useMemo(() => buildEnergyBalanceOption(data), [data]);
  const { window } = data;

  if (window.status === "no_logging") {
    return <p className="text-sm text-ink-muted">摂取の記録がありません。</p>;
  }

  const status = headerStatus(data);
  const calibration = calibrationText(data.calibration.status);
  const provisional =
    window.provisional_days > 0 ? ` · 暫定${window.provisional_days}日` : "";

  return (
    <div className="flex flex-col gap-4">
      {window.status === "ok" && (
        <dl className="grid grid-cols-3 gap-4">
          <Reading
            label="平均収支"
            value={formatSigned(window.mean_balance_kcal, 0)}
            sub={`${window.paired_days}/${data.window_days}日${provisional}`}
          />
          <Reading
            label="摂取"
            value={formatNumber(window.mean_intake_kcal, 0)}
          />
          <Reading
            label="消費"
            value={formatNumber(window.mean_expenditure_kcal, 0)}
          />
        </dl>
      )}
      <div className="flex flex-col gap-1">
        <ChartHeader
          title="日ごとの収支"
          note={bandNote(data)}
          status={status.text}
          statusTone={status.tone}
        />
        <EChart
          option={option}
          ariaLabel="日ごとのエネルギー収支グラフ"
          height={CHART_HEIGHT}
        />
      </div>
      {calibration != null && (
        <p className="text-xs text-ink-muted">{calibration}</p>
      )}
    </div>
  );
}
