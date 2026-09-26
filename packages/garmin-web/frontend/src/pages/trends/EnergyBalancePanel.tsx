import { Fragment, useMemo } from "react";
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
  COMPARE_COLOR,
  INK_COLOR,
  PAPER_COLOR,
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

/** The y axis is rounded out to multiples of this, so its ticks read as round numbers. */
const Y_STEP = 500;

/** Round `value` out to a multiple of {@link Y_STEP} (never returning -0). */
function roundOut(value: number, direction: "down" | "up"): number {
  const steps =
    direction === "down" ? Math.floor(value / Y_STEP) : Math.ceil(value / Y_STEP);
  return steps === 0 ? 0 : steps * Y_STEP;
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
  const bars = days.map((day) => (day.used ? day.balance_kcal : null));

  // The extent keeps the band and zero in view even when every bar sits outside
  // them, rounded out so the extremes are not printed as ticks (-1,173 / 251)
  // and the tallest bar does not touch the frame (#1441).
  const values = bars.filter((value): value is number => value != null);
  const yMin = roundOut(Math.min(...values, band?.[0] ?? 0, 0), "down");
  const yMax = roundOut(Math.max(...values, band?.[1] ?? 0, 0), "up");
  const yInterval =
    Y_STEP * Math.max(1, Math.ceil((yMax - yMin) / Y_STEP / 4));

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
        // Seven dates fit a phone-width strip; dropping every other one (the
        // shared hideOverlap) would also drop an excluded day's reason.
        interval: 0,
        hideOverlap: false,
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
      min: yMin,
      max: yMax,
      interval: yInterval,
      ...AXIS_STYLE,
      axisLabel: {
        ...AXIS_STYLE.axisLabel,
        // No digit grouping, like every other number on the page.
        formatter: (value: number) => formatNumber(value, 0),
      },
    },
    series: [
      {
        name: "収支",
        type: "bar",
        data: bars,
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
              // Inside the plot, above the line's right end: the default `end`
              // sits past the frame and was clipped to 「平」 (#1441). At phone
              // width a bar fills most of its column, so wherever the label
              // sits it crosses a bar; the paper ground keeps it readable
              // there instead of printing brown on ink (#1443).
              position: "insideEndTop",
              formatter: "平均",
              fontFamily: CHART_FONT_FAMILY,
              fontSize: CHART_FONT_SIZE,
              color: offTarget ? THRESHOLD_LINE.warn : COMPARE_COLOR,
              backgroundColor: PAPER_COLOR,
              padding: [1, 3],
            },
            data: [{ yAxis: mean }],
          },
        }),
      },
    ],
  };
}

/**
 * One reading of the window (the 体組成 `Reading` style, without a swatch).
 * The unit and each sub-line segment wrap whole: in a phone-width third of the
 * row, 「kcal/日」 and 「暫定6日」 used to break before their last character (#1441).
 */
function Reading({
  label,
  value,
  sub = [],
}: {
  label: string;
  value: string;
  /** Sub-line segments, joined by 「 · 」 and each kept on one line. */
  sub?: string[];
}) {
  return (
    <div>
      <dt className="font-mono text-xs text-ink-muted">{label}</dt>
      <dd className="mt-1 font-mono text-[20px] leading-none font-medium text-ink">
        {value}
        <span className="ml-[3px] font-sans text-[13px] whitespace-nowrap text-ink-muted">
          kcal/日
        </span>
      </dd>
      {sub.length > 0 && (
        <dd className="mt-1.5 font-mono text-xs text-ink-muted">
          {sub.map((segment, index) => (
            <Fragment key={segment}>
              {index > 0 && " · "}
              <span className="whitespace-nowrap">{segment}</span>
            </Fragment>
          ))}
        </dd>
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
  const coverage = [
    `${window.paired_days}/${data.window_days}日`,
    ...(window.provisional_days > 0 ? [`暫定${window.provisional_days}日`] : []),
  ];

  return (
    <div className="flex flex-col gap-4">
      {window.status === "ok" && (
        <dl className="grid grid-cols-3 gap-4">
          <Reading
            label="平均収支"
            value={formatSigned(window.mean_balance_kcal, 0)}
            sub={coverage}
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
