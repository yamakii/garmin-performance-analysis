import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  useActivities,
  useActivityDetail,
  useSections,
  useSectionVersions,
  useSplitAnomalies,
  useTimeSeries,
  useTrack,
} from "../api/hooks";
import { INK_COLOR, METRIC_COLORS } from "../components/chartTheme";
import Disclosure from "../components/Disclosure";
import MapPanel from "../components/MapPanel";
import { ErrorPanel, PageError, PageLoading } from "../components/PageState";
import SectionBlock from "../components/SectionBlock";
import SectionNav, { type NavItem } from "../components/SectionNav";
import EfficiencyReport from "../components/report/EfficiencyReport";
import EnvironmentReport from "../components/report/EnvironmentReport";
import FallbackFields from "../components/report/FallbackFields";
import PhaseTimeline from "../components/report/PhaseTimeline";
import ReportCard, { isRecord } from "../components/report/ReportCard";
import SplitNarrative from "../components/report/SplitNarrative";
import StarRating from "../components/report/StarRating";
import SummaryReport from "../components/report/SummaryReport";
import TimeSeriesChart from "../components/TimeSeriesChart";
import VersionSelect from "../components/VersionSelect";
import VitalsRow, { type VitalItem } from "../components/VitalsRow";
import { usePageTitle } from "../hooks/usePageTitle";
import type {
  ActivityDetailResponse,
  ActivitySummary,
  SectionsResponse,
  SplitAnomaliesResponse,
  SplitRow,
  TimeSeriesResponse,
} from "../types";
import {
  formatBpm,
  formatBpmValue,
  formatCadence,
  formatDistanceKmValue,
  formatDuration,
  formatFullDateLabel,
  formatPace,
  formatPaceValue,
  formatTimeOfDay,
  humanizeKey,
  PACE_UNIT,
} from "../utils/format";
import { formatNumber } from "../utils/formatNumber";
import { splitLead } from "../utils/leadSentence";

const AVAILABLE_METRICS: { key: string; label: string }[] = [
  { key: "heart_rate", label: "心拍数" },
  { key: "speed", label: "ペース" },
  { key: "cadence", label: "ケイデンス" },
  { key: "ground_contact_time", label: "接地時間" },
  { key: "power", label: "パワー" },
  { key: "elevation", label: "高度" },
  { key: "vertical_oscillation", label: "上下動" },
  { key: "vertical_ratio", label: "上下動比" },
];

const METRIC_LABELS: Record<string, string> = Object.fromEntries(
  AVAILABLE_METRICS.map(({ key, label }) => [key, label]),
);

/** Series shown before the reader asks for anything: the run's two axes. */
export const DEFAULT_METRICS = ["heart_rate", "speed"];

/**
 * Toggles offered up front. The rest (power, elevation and the two form
 * metrics) answer a follow-up question, so they stay behind a "+" link rather
 * than spending eight chips of attention on first read (#1118).
 */
export const PRIMARY_METRICS = [
  "heart_rate",
  "speed",
  "cadence",
  "ground_contact_time",
];

const SECONDARY_METRICS = AVAILABLE_METRICS.filter(
  ({ key }) => !PRIMARY_METRICS.includes(key),
);

/** "+ パワー / 高度 / 上下動 / 上下動比" — the label of that "+" link. */
const MORE_METRICS_LABEL = `+ ${SECONDARY_METRICS.map(
  (metric) => metric.label,
).join(" / ")}`;

/** Split rows shown before the table folds into a disclosure. */
const SPLIT_PREVIEW_ROWS = 10;

// Section types with dedicated report components; others fall back.
const KNOWN_SECTION_TYPES = [
  "summary",
  "split",
  "phase",
  "efficiency",
  "environment",
];

/**
 * Japanese heading for a section type. Analyses saved with a type this build
 * has no component for still get a readable title instead of the raw wire key
 * ("next_run_target" -> "next run target", Issue #915).
 */
const SECTION_TITLES: Record<string, string> = {
  summary: "総合評価",
  split: "スプリット",
  phase: "フェーズ評価",
  efficiency: "効率",
  environment: "環境影響",
};

export function sectionTitle(type: string): string {
  return SECTION_TITLES[type] ?? humanizeKey(type);
}

/** Binary search: index of the timestamp nearest to target (ascending). */
export function nearestTimestampIndex(
  timestamps: number[],
  target: number,
): number {
  let low = 0;
  let high = timestamps.length - 1;
  while (low < high) {
    const mid = (low + high) >> 1;
    if (timestamps[mid] < target) {
      low = mid + 1;
    } else {
      high = mid;
    }
  }
  if (low > 0 && target - timestamps[low - 1] <= timestamps[low] - target) {
    return low - 1;
  }
  return low;
}

/**
 * Splits shorter than this are lap-press fragments, not real kilometers: a
 * 5-11 m "split" reports an artifact pace (e.g. 4:04/km) that sits at the fast
 * extreme and would flatten every other bar (#873). They are excluded from the
 * normalization population and get no bar of their own.
 */
export const BAR_MIN_SPLIT_KM = 0.4;

/** Shortest bar, in percent — a floor so the extreme row still reads as a bar. */
const BAR_MIN_PCT = 12;

export interface BarScale {
  min: number;
  max: number;
}

/** Min/max of a split column over real (non-fragment) splits, or null. */
export function splitBarScale(
  splits: SplitRow[],
  key: "pace_seconds_per_km" | "heart_rate",
): BarScale | null {
  const values = splits
    .filter(
      (split) =>
        typeof split.distance === "number" &&
        split.distance >= BAR_MIN_SPLIT_KM,
    )
    .map((split) => split[key])
    .filter(
      (value): value is number =>
        typeof value === "number" && Number.isFinite(value) && value > 0,
    );
  if (values.length < 2) {
    return null;
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  // A flat column carries no comparison, so it gets no bars at all.
  return max > min ? { min, max } : null;
}

/**
 * Bar width for one cell, or null when it should render bare.
 *
 * `invert` maps the smaller value to the longer bar, which is what pace needs:
 * faster is better, so the fastest split should read as the longest bar.
 */
export function barWidthPct(
  value: number | null,
  scale: BarScale | null,
  invert: boolean,
): number | null {
  if (scale == null || typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }
  const clamped = Math.min(scale.max, Math.max(scale.min, value));
  const position = (clamped - scale.min) / (scale.max - scale.min);
  const ratio = invert ? 1 - position : position;
  return BAR_MIN_PCT + ratio * (100 - BAR_MIN_PCT);
}

/** The summary section's data, when it parsed into an object. */
function summaryData(
  sections: SectionsResponse | null,
): Record<string, unknown> | null {
  const data = sections?.summary?.data;
  return isRecord(data) ? data : null;
}

function summaryStarRating(sections: SectionsResponse | null): string | null {
  const data = summaryData(sections);
  return typeof data?.star_rating === "string" ? data.star_rating : null;
}

/** The summary's opening sentence: the page's conclusion line. */
function summaryLead(sections: SectionsResponse | null): string | null {
  const data = summaryData(sections);
  if (typeof data?.summary !== "string") {
    return null;
  }
  const { lead } = splitLead(data.summary);
  return lead !== "" ? lead : null;
}

/** "上限 150bpm" / "処方上限 150bpm" as written in a verdict reason. */
const HR_CEILING_IN_REASON = /上限\s*(\d+(?:\.\d+)?)\s*bpm/;

/**
 * The HR ceiling the day was prescribed, or null when the day carried no
 * prescription (Morning Brief, #1118).
 *
 * The number is not a column on the activity: `compute_prescription_verdict`
 * writes it into the Japanese reasons it hands the summary agent ("平均HR
 * 148bpm が処方上限 150bpm を …"), which is what reaches the browser. Reading
 * it back from there keeps the header, the chart's dotted cap line and the
 * verdict quoting one and the same number instead of three. A run without a
 * recorded heart rate has nothing to hold against a cap, so it gets none.
 */
export function hrCeilingOf(
  detail: ActivityDetailResponse,
  sections: SectionsResponse | null,
): number | null {
  // A cap is only a reading when there are beats to read against it.
  if (detail.activity.avg_heart_rate == null) {
    return null;
  }
  const verdict = summaryData(sections)?.prescription_verdict;
  if (!isRecord(verdict) || !Array.isArray(verdict.reasons)) {
    return null;
  }
  for (const reason of verdict.reasons) {
    const match =
      typeof reason === "string" ? HR_CEILING_IN_REASON.exec(reason) : null;
    if (match != null) {
      return Number(match[1]);
    }
  }
  return null;
}

/**
 * Gaps longer than this are a pause or a dropout, not time spent running: a
 * sample on either side of one says nothing about the minutes between them.
 */
const MAX_SAMPLE_GAP_S = 60;

/**
 * Seconds spent above the prescribed HR ceiling, or null when either the
 * series or the ceiling is missing.
 *
 * "心拍が高め" is an impression; "上限 150 · 超過 12:34" is the same statement
 * with a size, and the size is what decides whether the run needs an answer.
 * Each sample contributes the gap to the next one, so an unevenly sampled
 * series is measured in seconds rather than in samples.
 */
export function secondsOverCeiling(
  series: TimeSeriesResponse | null,
  ceiling: number | null,
): number | null {
  if (series == null || ceiling == null) {
    return null;
  }
  const values = series.metrics.heart_rate;
  if (values == null) {
    return null;
  }
  const timestamps = series.timestamps;
  let seconds = 0;
  for (let i = 0; i < values.length; i += 1) {
    const value = values[i];
    if (value == null || value <= ceiling) {
      continue;
    }
    const next = timestamps[i + 1];
    const current = timestamps[i];
    const gap =
      next != null && current != null
        ? next - current
        : // The last sample stands for the same interval as the one before it.
          (current ?? 0) - (timestamps[i - 1] ?? current ?? 0);
    if (gap > 0 && gap <= MAX_SAMPLE_GAP_S) {
      seconds += gap;
    }
  }
  return seconds;
}

/** Metrics compared against the last run of the same type, in reading order. */
const VS_PREVIOUS_METRICS: { key: string; label: string; unit: string }[] = [
  { key: "pace_s_per_km", label: "ペース", unit: "秒/km" },
  { key: "avg_hr", label: "HR", unit: "bpm" },
  { key: "gct_ms", label: "GCT", unit: "ms" },
  { key: "cadence_spm", label: "ケイデンス", unit: "spm" },
];

/**
 * "前回比(7日前・5.07km): ペース -10秒/km · HR -3bpm · GCT +4ms · ケイデンス -2spm"
 *
 * One mono line under the numbers instead of a row of chips (#1118): the
 * deltas are context for the KPIs above them, and they stay uncolored —
 * whether a delta is good depends on the metric and on the session's intent,
 * and that reading belongs to the prose.
 *
 * The comparison run is named by how long ago it was and how far it went: a
 * pace delta against a 5km means something different from the same delta
 * against a 22km, and the saved payload carries only the id and the gap in
 * days (#1153). The distance is looked up in the activity list; when the run
 * is outside the list the head falls back to the days alone rather than
 * blocking the line.
 */
function vsPreviousLine(
  sections: SectionsResponse | null,
  activities: ActivitySummary[],
): string | null {
  const data = summaryData(sections)?.vs_previous;
  if (!isRecord(data)) {
    return null;
  }
  const parts = VS_PREVIOUS_METRICS.map(({ key, label, unit }) => {
    const metric = data[key];
    const delta = isRecord(metric) ? metric.delta : null;
    if (typeof delta !== "number" || !Number.isFinite(delta)) {
      return null;
    }
    const sign = delta > 0 ? "+" : delta === 0 ? "±" : "";
    return `${label} ${sign}${formatNumber(delta)}${unit}`;
  }).filter((part): part is string => part != null);
  if (parts.length === 0) {
    return null;
  }
  const daysAgo = typeof data.days_ago === "number" ? data.days_ago : null;
  const previousId =
    typeof data.previous_activity_id === "number"
      ? data.previous_activity_id
      : null;
  const previousKm = activities.find(
    (activity) => activity.activity_id === previousId,
  )?.total_distance_km;
  const distance =
    previousKm != null ? `・${formatDistanceKmValue(previousKm)}km` : "";
  const head = daysAgo != null ? `前回比（${daysAgo}日前${distance}）` : "前回比";
  return `${head}: ${parts.join(" · ")}`;
}

/**
 * The mono line above the headline: when the run happened, what it answered,
 * and the two physiology numbers that frame it.
 *
 * The threshold shown is the one configured on the watch — the value the
 * zones, the prescriptions and the athlete all run to, recorded as the lower
 * bound of zone 5. Garmin's own auto-detected estimate is deliberately NOT
 * shown: it disagrees with the configured value (164 vs 170), it can sit
 * frozen for months, and next to a zone table built from 170 it leaves the
 * reader unable to tell which number is their threshold (#1098).
 */
function metaLine(
  detail: ActivityDetailResponse,
  sections: SectionsResponse | null,
): string {
  const parts = [formatFullDateLabel(detail.activity.activity_date)];
  // When the run started, in local time: the same day can hold a 06:00 easy
  // and a 13:45 long, and heat, HR and the prescription all read differently
  // for each (#1153). A run without a recorded start simply omits it.
  const startedAt = detail.activity.start_time_local;
  const clock = formatTimeOfDay(
    typeof startedAt === "string" ? startedAt : null,
  );
  if (clock != null) {
    parts.push(clock);
  }
  const verdict = summaryData(sections)?.prescription_verdict;
  const title = isRecord(verdict) ? verdict.prescription_title : null;
  if (typeof title === "string" && title !== "") {
    parts.push(`処方「${title}」`);
  }
  if (detail.vo2_max?.value != null) {
    parts.push(`VO2max ${detail.vo2_max.value.toFixed(1)}`);
  }
  const configuredLthr = detail.hr_zones.find(
    (zone) => zone.zone_number === 5,
  )?.zone_low_boundary;
  if (configuredLthr != null) {
    parts.push(`乳酸閾値（設定値）${formatBpm(configuredLthr)}`);
  }
  return parts.join(" · ");
}

/** The four numbers of the run, with the prescribed cap read against them. */
function kpiItems(
  detail: ActivityDetailResponse,
  ceiling: number | null,
  overSeconds: number | null,
): VitalItem[] {
  const { activity } = detail;
  const ceilingNote =
    ceiling == null
      ? undefined
      : overSeconds != null && overSeconds > 0
        ? `上限 ${formatNumber(ceiling, 0)} · 超過 ${formatDuration(overSeconds)}`
        : `上限 ${formatNumber(ceiling, 0)}`;
  return [
    {
      label: "距離",
      value: formatDistanceKmValue(activity.total_distance_km),
      unit: "km",
    },
    {
      label: "時間",
      value: formatDuration(activity.total_time_seconds),
    },
    {
      label: "平均ペース",
      value: formatPaceValue(activity.avg_pace_seconds_per_km),
      unit: PACE_UNIT,
    },
    {
      label: "平均心拍",
      value: formatBpmValue(activity.avg_heart_rate),
      unit: "bpm",
      note: ceilingNote,
      noteTone:
        overSeconds != null && overSeconds > 0 && ceiling != null
          ? "warn"
          : "muted",
    },
  ];
}

/**
 * Numeric split cell backed by a subtle proportional bar (#905).
 *
 * The bar is positioned against an inner box rather than the cell, so a 100%
 * bar stops at the cell's padding instead of running into the neighbouring
 * column's bar and reading as one continuous band (#1145).
 */
export function BarCell({
  widthPct,
  color,
  flagged,
  children,
}: {
  widthPct: number | null;
  color: string;
  flagged: boolean;
  children: string;
}) {
  return (
    <td className="px-2 py-2 text-right">
      <div className="relative">
        {widthPct != null && (
          <span
            aria-hidden="true"
            className="absolute -inset-y-1 left-0 rounded-sm"
            style={{
              width: `${widthPct.toFixed(1)}%`,
              backgroundColor: `${color}24`,
            }}
          />
        )}
        <span
          className={`relative ${flagged ? "font-semibold text-status-warn" : ""}`}
        >
          {children}
        </span>
      </div>
    </td>
  );
}

/** Shared hover state in the seq_no / timestamp_s domain. */
interface HoverState {
  source: "chart" | "map";
  value: number;
}

const SPLIT_COLUMNS = [
  "#",
  "距離",
  "ペース",
  "心拍",
  "ケイデンス",
  "パワー",
];

/**
 * Splits worth the reader's eye, keyed to the metrics that moved (#1132).
 *
 * Only *material* anomalies (identifiable cause, |z| > 3.5) tint a row — the
 * detector's low-severity spikes fire at their chance base rate even on healthy
 * form, so highlighting them would tint half the table. A missing or failed
 * response yields an empty map: a table with nothing to highlight is the normal
 * case, not an error.
 */
export function flaggedSplitMetrics(
  anomalies: SplitAnomaliesResponse | undefined,
): Map<number, string[]> {
  const flagged = new Map<number, string[]>();
  for (const split of anomalies?.splits ?? []) {
    if (split.material > 0) {
      flagged.set(split.split_index, split.metrics);
    }
  }
  return flagged;
}

/**
 * The splits table (Morning Brief, #1118): mono figures between rules, with
 * the inline pace / HR bars kept so the run reads as a shape, and the
 * kilometres whose form actually moved tinted so the exceptions can be found
 * without reading every row.
 *
 * `flagged` maps a split number to the form metrics the detector flagged there
 * (#1132), which become the row's tooltip.
 */
function SplitsTable({
  splits,
  paceScale,
  hrScale,
  flagged,
  caption,
}: {
  splits: SplitRow[];
  paceScale: BarScale | null;
  hrScale: BarScale | null;
  flagged: Map<number, string[]>;
  caption: string;
}) {
  return (
    // Six numeric columns overflow a ~360px screen: the wrapper scrolls the
    // table instead of letting the page scroll sideways (#912). The minimum
    // width keeps the columns (and their bars) apart at 390px rather than
    // letting them compress into each other (#1145).
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] font-mono text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-ink text-[11px] tracking-[0.04em] text-ink-muted">
            {SPLIT_COLUMNS.map((column, index) => (
              <th
                key={column}
                scope="col"
                className={`px-2 py-2 font-medium ${
                  index === 0 ? "text-left" : "text-right"
                }`}
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {splits.map((split) => {
            // Fragment rows keep their numbers but never draw a bar: their
            // pace is an artifact of a manual lap press.
            const isFragment =
              typeof split.distance !== "number" ||
              split.distance < BAR_MIN_SPLIT_KM;
            const flaggedMetrics = flagged.get(split.split_index);
            const isFlagged = flaggedMetrics != null;
            return (
              <tr
                key={split.split_index}
                className={`border-b border-hairline ${
                  isFlagged ? "bg-warn-tint" : "hover:bg-surface"
                }`}
                title={
                  isFlagged
                    ? `フォーム異常: ${flaggedMetrics.join(", ")}`
                    : undefined
                }
              >
                <td className="px-2 py-2 text-left text-ink-muted">
                  {split.split_index}
                </td>
                <td className="px-2 py-2 text-right">
                  {formatDistanceKmValue(split.distance)}
                </td>
                <BarCell
                  widthPct={
                    isFragment
                      ? null
                      : barWidthPct(split.pace_seconds_per_km, paceScale, true)
                  }
                  color={METRIC_COLORS.speed}
                  flagged={isFlagged}
                >
                  {formatPace(split.pace_seconds_per_km)}
                </BarCell>
                <BarCell
                  widthPct={
                    isFragment
                      ? null
                      : barWidthPct(split.heart_rate, hrScale, false)
                  }
                  color={METRIC_COLORS.heart_rate}
                  flagged={isFlagged}
                >
                  {formatBpmValue(split.heart_rate)}
                </BarCell>
                <td className="px-2 py-2 text-right">
                  {formatCadence(split.cadence)}
                </td>
                <td className="px-2 py-2 text-right">
                  {formatNumber(split.power, 0)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/**
 * One run, read top-down (Morning Brief, #1118): what it was and how it went
 * (header), the assessment, then the evidence — the series, the course, the
 * splits, the phases and the form numbers — each as a labelled section.
 */
export default function ActivityDetail() {
  const { id } = useParams<{ id: string }>();
  const [selectedMetrics, setSelectedMetrics] =
    useState<string[]>(DEFAULT_METRICS);
  const [showAllMetrics, setShowAllMetrics] = useState(false);
  const [hover, setHover] = useState<HoverState | null>(null);
  // null = latest; otherwise pin sections to a past analysis batch's created_at.
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);

  const detailQuery = useActivityDetail(id);
  const versionsQuery = useSectionVersions(id);
  const sectionsQuery = useSections(id, selectedRunId ?? undefined);
  // The time-series query only runs when at least one metric is selected;
  // otherwise it stays idle and the chart shows its empty-state placeholder.
  const timeSeriesQuery = useTimeSeries(id, selectedMetrics);
  const trackQuery = useTrack(id);
  // Splits-table highlighting only; a failure leaves the table plain rather
  // than blocking the page (#1132).
  const splitAnomaliesQuery = useSplitAnomalies(id);
  // The list is read only to name the comparison run's distance; it is the
  // same cached query the activity list uses, so this costs nothing on a
  // reader who arrived from there, and a failure only drops the distance.
  const activitiesQuery = useActivities();

  const loading = detailQuery.isPending || sectionsQuery.isPending;
  // A failed activity / sections fetch is fatal (full-page error); the
  // time-series and track panels degrade individually instead.
  const fatalError = detailQuery.error ?? sectionsQuery.error;
  const detail = detailQuery.data ?? null;
  const sections = sectionsQuery.data ?? null;
  // The activity names the tab; until it lands the previous title stands.
  usePageTitle(detail?.activity.activity_name ?? undefined);
  const versions = versionsQuery.data ?? [];
  // The selected run index: 0 (latest) unless a past run_id is pinned.
  const selectedVersionIndex =
    selectedRunId == null
      ? 0
      : Math.max(
          0,
          versions.findIndex((v) => v.run_id === selectedRunId),
        );

  const handleVersionChange = (index: number) => {
    // Index 0 is the newest run → clear the pin so we always track "latest".
    setSelectedRunId(index === 0 ? null : versions[index].run_id);
  };

  const hasMetrics = selectedMetrics.length > 0;
  const timeSeries = hasMetrics ? (timeSeriesQuery.data ?? null) : null;
  const timeSeriesError =
    hasMetrics && timeSeriesQuery.error != null
      ? timeSeriesQuery.error.message
      : null;
  const track = trackQuery.data?.points ?? null;
  const trackError =
    trackQuery.error != null ? trackQuery.error.message : null;

  const toggleMetric = (key: string) => {
    setSelectedMetrics((current) =>
      current.includes(key)
        ? current.filter((metric) => metric !== key)
        : [
            ...AVAILABLE_METRICS.map((metric) => metric.key).filter(
              (metric) => current.includes(metric) || metric === key,
            ),
          ],
    );
  };

  if (loading) {
    return <PageLoading />;
  }
  if (fatalError) {
    return (
      <PageError
        error={fatalError}
        // Either fetch can be the failing one, and both are required for the
        // page to render — so a retry re-runs the pair.
        onRetry={() => {
          void detailQuery.refetch();
          void sectionsQuery.refetch();
        }}
      />
    );
  }
  if (!detail) {
    return (
      <p className="rounded-md border border-hairline px-4 py-12 text-center text-sm text-ink-muted">
        アクティビティが見つかりません
      </p>
    );
  }

  const { splits } = detail;

  // Inline bars let the splits table be read as a shape (#905). Both columns
  // are min-max normalized over the real splits only.
  const paceScale = splitBarScale(splits, "pace_seconds_per_km");
  const hrScale = splitBarScale(splits, "heart_rate");
  const flaggedSplits = flaggedSplitMetrics(splitAnomaliesQuery.data);

  // Bidirectional hover sync: chart data index <-> track seq_no, matched
  // through the nearest timestamp / seq_no value.
  const timestamps = timeSeries?.timestamps ?? [];
  const chartHoverIndex =
    hover?.source === "map" && timestamps.length > 0
      ? nearestTimestampIndex(timestamps, hover.value)
      : null;
  const mapHoverSeqNo = hover?.value ?? null;

  const handleChartHover = (index: number | null) => {
    setHover(
      index == null || timestamps.length === 0
        ? null
        : { source: "chart", value: timestamps[index] ?? index },
    );
  };

  const handleMapHover = (seqNo: number | null) => {
    setHover(seqNo == null ? null : { source: "map", value: seqNo });
  };

  const starRating = summaryStarRating(sections);
  const lead = summaryLead(sections);
  const hrCeiling = hrCeilingOf(detail, sections);
  const overSeconds = secondsOverCeiling(timeSeries, hrCeiling);
  const vsPrevious = vsPreviousLine(sections, activitiesQuery.data ?? []);
  const unknownSectionTypes = sections
    ? Object.keys(sections).filter(
        (type) => !KNOWN_SECTION_TYPES.includes(type),
      )
    : [];

  // In-page nav: list only the sections that actually render below, so the
  // table of contents never points at a missing anchor.
  const hasTrack = track != null && track.length > 0;
  // The course section also renders (as an error panel) when the track
  // fetch failed, so the nav anchor stays valid in that state too.
  const showCourse = hasTrack || trackError !== null;
  const hasSplits = splits.length > 0 || Boolean(sections?.split);
  const navItems: NavItem[] = [
    sections?.summary ? { id: "section-overview", label: "総合評価" } : null,
    { id: "section-timeseries", label: "タイムシリーズ" },
    showCourse ? { id: "section-course", label: "コース" } : null,
    hasSplits ? { id: "section-splits", label: "スプリット" } : null,
    sections?.phase ? { id: "section-phase", label: "フェーズ評価" } : null,
    sections?.efficiency
      ? { id: "section-efficiency", label: "効率分析" }
      : null,
    sections?.environment
      ? { id: "section-environment", label: "環境影響" }
      : null,
  ].filter((item): item is NavItem => item !== null);

  const visibleMetrics = showAllMetrics
    ? AVAILABLE_METRICS
    : AVAILABLE_METRICS.filter(({ key }) => PRIMARY_METRICS.includes(key));
  const previewSplits = splits.slice(0, SPLIT_PREVIEW_ROWS);
  const foldedSplits = splits.slice(SPLIT_PREVIEW_ROWS);

  return (
    <div className="flex flex-col gap-12">
      {/* Header: where this run sits, what it was, and how it went */}
      <header className="flex flex-col gap-4">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2">
          <Link to="/activities" className="font-mono text-[13px]">
            ← 一覧へ
          </Link>
          {/* Analysis version picker — shown only when a re-analysis exists (#720) */}
          <VersionSelect
            id="section-version-select"
            options={versions.map((version) => ({
              key: String(version.run_id),
              stamp: version.created_at,
            }))}
            selectedIndex={selectedVersionIndex}
            onSelect={handleVersionChange}
          />
        </div>
        <p className="font-mono text-[13px] text-ink-muted">
          {metaLine(detail, sections)}
        </p>
        {/* 36px at every width: 40px is the home page's verdict size, and a
            run's name is a heading, not the page's conclusion (#1153). */}
        <h1 className="flex flex-wrap items-baseline gap-x-4 gap-y-2 text-[36px] leading-[1.15] font-bold tracking-[-0.01em] text-ink">
          {detail.activity.activity_name ?? "アクティビティ"}
          {starRating != null && <StarRating text={starRating} size="lg" />}
        </h1>
        {lead != null && (
          <p className="max-w-[720px] text-lg leading-[1.6] text-ink-soft">
            {lead}
          </p>
        )}
        <VitalsRow
          ariaLabel="このランの数値"
          items={kpiItems(detail, hrCeiling, overSeconds)}
          size="lg"
        />
        {vsPrevious != null && (
          <p className="font-mono text-[13px] text-ink-muted">{vsPrevious}</p>
        )}
      </header>

      {/* Sticky in-page table of contents (rendered sections only) */}
      <SectionNav items={navItems} />

      {/* Overall assessment report */}
      <SummaryReport id="section-overview" section={sections?.summary} />

      {/* Time series chart with metric toggles */}
      <SectionBlock id="section-timeseries" title="タイムシリーズ">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          {visibleMetrics.map(({ key, label }) => {
            const checked = selectedMetrics.includes(key);
            // An active toggle is ink-filled and carries a short bar in the
            // metric's chart color, matching its line below; the label itself
            // stays paper-on-ink so it clears AA (#911, #1116).
            const color = METRIC_COLORS[key] ?? INK_COLOR;
            return (
              <label
                key={key}
                className={`inline-flex cursor-pointer items-center gap-1.5 rounded-sm px-2.5 py-1 font-mono text-xs transition-colors ${
                  checked
                    ? "bg-ink text-paper"
                    : "border border-hairline text-ink-soft hover:bg-surface"
                }`}
              >
                <input
                  type="checkbox"
                  className="sr-only"
                  checked={checked}
                  onChange={() => toggleMetric(key)}
                />
                {checked && (
                  <span
                    aria-hidden="true"
                    className="inline-block h-0.5 w-3.5"
                    style={{ backgroundColor: color }}
                  />
                )}
                {label}
              </label>
            );
          })}
          {!showAllMetrics && (
            <button
              type="button"
              onClick={() => setShowAllMetrics(true)}
              className="px-1 py-1 font-mono text-xs text-accent hover:underline"
            >
              {MORE_METRICS_LABEL}
            </button>
          )}
        </div>
        {timeSeriesError !== null ? (
          <ErrorPanel
            message={`読み込みに失敗しました: ${timeSeriesError}`}
            onRetry={() => {
              void timeSeriesQuery.refetch();
            }}
          />
        ) : timeSeries && Object.keys(timeSeries.metrics).length > 0 ? (
          <TimeSeriesChart
            data={timeSeries}
            metricLabels={METRIC_LABELS}
            hoverIndex={chartHoverIndex}
            onHoverIndex={handleChartHover}
            hrCeiling={hrCeiling}
          />
        ) : (
          <p className="py-8 text-center text-sm text-ink-muted">
            表示する指標を選択してください
          </p>
        )}
      </SectionBlock>

      {/* GPS track map — omitted entirely when the activity has no GPS data
          (successful empty fetch); shown as an error panel when the fetch failed */}
      {showCourse && (
        <SectionBlock id="section-course" title="コース">
          {trackError === null && track != null ? (
            <MapPanel
              points={track}
              hoverSeqNo={mapHoverSeqNo}
              onHoverSeqNo={handleMapHover}
            />
          ) : (
            <ErrorPanel
              message={`読み込みに失敗しました: ${trackError ?? "不明なエラー"}`}
              onRetry={() => {
                void trackQuery.refetch();
              }}
            />
          )}
        </SectionBlock>
      )}

      {/* Splits: table + per-split narrative from the split analyst */}
      {hasSplits && (
        <SectionBlock
          id="section-splits"
          title="スプリット"
          note={
            flaggedSplits.size > 0
              ? `注意 ${flaggedSplits.size}本`
              : undefined
          }
          noteMono
        >
          {previewSplits.length > 0 && (
            <SplitsTable
              splits={previewSplits}
              paceScale={paceScale}
              hrScale={hrScale}
              flagged={flaggedSplits}
              caption={
                foldedSplits.length > 0
                  ? `スプリット 1–${previewSplits.length}`
                  : "スプリット"
              }
            />
          )}
          {foldedSplits.length > 0 ? (
            <Disclosure
              className="mt-3"
              title={`全 ${splits.length} スプリットと解説を表示`}
            >
              <SplitsTable
                splits={foldedSplits}
                paceScale={paceScale}
                hrScale={hrScale}
                flagged={flaggedSplits}
                caption={`スプリット ${SPLIT_PREVIEW_ROWS + 1}–${splits.length}`}
              />
              <SplitNarrative section={sections?.split} />
            </Disclosure>
          ) : (
            <SplitNarrative section={sections?.split} />
          )}
        </SectionBlock>
      )}

      {/* Phase evaluation rows */}
      <PhaseTimeline id="section-phase" section={sections?.phase} />

      {/* Efficiency: structured form stats + analyst prose */}
      <EfficiencyReport
        id="section-efficiency"
        section={sections?.efficiency}
        formEvaluations={detail.form_evaluations}
      />

      {/* Environmental impact */}
      <EnvironmentReport
        id="section-environment"
        section={sections?.environment}
      />

      {/* Unknown section types degrade to key-value cards */}
      {sections &&
        unknownSectionTypes.map((type) => (
          <ReportCard
            key={type}
            title={sectionTitle(type)}
            section={sections[type]}
          >
            {(data) => <FallbackFields data={data} exclude={["metadata"]} />}
          </ReportCard>
        ))}
    </div>
  );
}
