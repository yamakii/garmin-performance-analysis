import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  useActivityDetail,
  useSections,
  useSectionVersions,
  useTimeSeries,
  useTrack,
} from "../api/hooks";
import { CARD_CLASS } from "../components/Card";
import { METRIC_COLORS, METRIC_TEXT_COLORS } from "../components/chartTheme";
import HeroHeader from "../components/HeroHeader";
import MapPanel from "../components/MapPanel";
import { PageError, PageLoading } from "../components/PageState";
import SectionNav, { type NavItem } from "../components/SectionNav";
import EfficiencyReport from "../components/report/EfficiencyReport";
import EnvironmentReport from "../components/report/EnvironmentReport";
import FallbackFields from "../components/report/FallbackFields";
import PhaseTimeline from "../components/report/PhaseTimeline";
import ReportCard, { isRecord } from "../components/report/ReportCard";
import SplitNarrative from "../components/report/SplitNarrative";
import SummaryReport from "../components/report/SummaryReport";
import TimeSeriesChart from "../components/TimeSeriesChart";
import { usePageTitle } from "../hooks/usePageTitle";
import type { SectionsResponse, SplitRow } from "../types";
import { formatNumber } from "../utils/formatNumber";
import { formatCadence, formatDistance, formatPace } from "./ActivityList";

const AVAILABLE_METRICS: { key: string; label: string }[] = [
  { key: "heart_rate", label: "心拍数" },
  { key: "speed", label: "ペース" },
  { key: "cadence", label: "ケイデンス" },
  { key: "power", label: "パワー" },
  { key: "elevation", label: "高度" },
  { key: "ground_contact_time", label: "接地時間" },
  { key: "vertical_oscillation", label: "上下動" },
  { key: "vertical_ratio", label: "上下動比" },
];

const METRIC_LABELS: Record<string, string> = Object.fromEntries(
  AVAILABLE_METRICS.map(({ key, label }) => [key, label]),
);

const DEFAULT_METRICS = ["heart_rate", "speed"];

// Section types with dedicated report components; others fall back.
const KNOWN_SECTION_TYPES = [
  "summary",
  "split",
  "phase",
  "efficiency",
  "environment",
];

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

/** Numeric split cell backed by a subtle proportional bar (#905). */
function BarCell({
  widthPct,
  color,
  children,
}: {
  widthPct: number | null;
  color: string;
  children: string;
}) {
  return (
    <td className="relative px-2 py-2 text-right tabular-nums">
      {widthPct != null && (
        <span
          aria-hidden="true"
          className="absolute inset-y-1 left-0 rounded-sm"
          style={{
            width: `${widthPct.toFixed(1)}%`,
            backgroundColor: `${color}1f`,
          }}
        />
      )}
      <span className="relative">{children}</span>
    </td>
  );
}

/** Shared hover state in the seq_no / timestamp_s domain. */
interface HoverState {
  source: "chart" | "map";
  value: number;
}

function summaryStarRating(sections: SectionsResponse | null): string | null {
  const data = sections?.summary?.data;
  if (isRecord(data) && typeof data.star_rating === "string") {
    return data.star_rating;
  }
  return null;
}

/** Per-panel fetch failure: alert message + retry, shown in place of the content. */
function PanelError({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-8 text-sm text-red-700"
    >
      <p>読み込みに失敗しました: {message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="rounded-lg border border-red-300 bg-white px-4 py-1.5 font-medium text-red-700 transition-colors hover:bg-red-100"
      >
        再試行
      </button>
    </div>
  );
}

export default function ActivityDetail() {
  const { id } = useParams<{ id: string }>();
  const [selectedMetrics, setSelectedMetrics] =
    useState<string[]>(DEFAULT_METRICS);
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
      <p className="rounded-xl border border-slate-200 bg-white px-4 py-12 text-center text-sm text-slate-500 shadow-sm">
        アクティビティが見つかりません
      </p>
    );
  }

  const { splits } = detail;

  // Inline bars let the splits table be read as a shape (#905). Both columns
  // are min-max normalized over the real splits only.
  const paceScale = splitBarScale(splits, "pace_seconds_per_km");
  const hrScale = splitBarScale(splits, "heart_rate");

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

  return (
    <div className="stagger-in space-y-6">
      {/* Report hero: back link, display headline, gold stars, KPI strip */}
      <div>
        <Link
          to="/activities"
          className="text-sm font-medium text-ink/70 hover:text-ink"
        >
          ← アクティビティ一覧
        </Link>
        <div className="mt-2">
          <HeroHeader detail={detail} starRating={starRating} />
        </div>
      </div>

      {/* Analysis version selector — shown only when a re-analysis exists (#720) */}
      {versions.length > 1 && (
        <div className="flex flex-wrap items-center gap-3">
          <label
            htmlFor="section-version-select"
            className="text-sm font-medium text-slate-500"
          >
            分析版を選択:
          </label>
          <select
            id="section-version-select"
            value={selectedVersionIndex}
            onChange={(e) => handleVersionChange(Number(e.target.value))}
            // A visible focus indicator, not a removed one (#912): the old
            // `focus:outline-none` dropped the UA ring and replaced it with a
            // border tint that barely reads. The ring is keyboard-only.
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-ink shadow-sm focus-visible:border-ink focus-visible:ring-2 focus-visible:ring-ink/50 focus-visible:outline-none"
          >
            {versions.map((version, i) => (
              <option key={version.run_id} value={i}>
                {i === 0
                  ? `${version.created_at}（最新）`
                  : version.created_at}
              </option>
            ))}
          </select>
          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">
            全{versions.length}版
          </span>
        </div>
      )}

      {/* Sticky in-page table of contents (rendered sections only) */}
      <SectionNav items={navItems} />

      {/* Overall assessment report */}
      {sections?.summary && (
        <div id="section-overview" className="scroll-mt-20">
          <SummaryReport section={sections.summary} />
        </div>
      )}

      {/* Time series chart with metric toggles */}
      <section
        id="section-timeseries"
        className={`scroll-mt-20 ${CARD_CLASS}`}
      >
        <h2 className="mb-3 font-display text-base font-semibold text-ink">
          タイムシリーズ
        </h2>
        <div className="mb-4 flex flex-wrap gap-2">
          {AVAILABLE_METRICS.map(({ key, label }) => {
            const checked = selectedMetrics.includes(key);
            // Active toggles carry the metric's semantic color (Issue #214),
            // matching its line color in the chart below. Tint, border and the
            // checkbox keep the vivid chart hue (non-text, >=3:1); the label
            // takes the darkened on-light variant so it clears AA (#911).
            const color = METRIC_COLORS[key] ?? "#16213a";
            const textColor = METRIC_TEXT_COLORS[key] ?? "#16213a";
            return (
              <label
                key={key}
                className={`inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-sm transition-colors ${
                  checked
                    ? "font-medium"
                    : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                }`}
                style={
                  checked
                    ? {
                        color: textColor,
                        borderColor: `${color}4d`,
                        backgroundColor: `${color}14`,
                      }
                    : undefined
                }
              >
                <input
                  type="checkbox"
                  style={{ accentColor: color }}
                  checked={checked}
                  onChange={() => toggleMetric(key)}
                />
                {label}
              </label>
            );
          })}
        </div>
        {timeSeriesError !== null ? (
          <PanelError
            message={timeSeriesError}
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
          />
        ) : (
          <p className="py-8 text-center text-sm text-slate-500">
            表示する指標を選択してください
          </p>
        )}
      </section>

      {/* GPS track map — omitted entirely when the activity has no GPS data
          (successful empty fetch); shown as an error panel when the fetch failed */}
      {showCourse && (
        <section
          id="section-course"
          className="scroll-mt-20 rounded-xl border border-slate-200 bg-white shadow-sm"
        >
          <h2 className="px-5 pt-4 pb-2 font-display text-base font-semibold text-ink">
            コース
          </h2>
          {trackError === null && track != null ? (
            <div className="overflow-hidden rounded-b-xl">
              <MapPanel
                points={track}
                hoverSeqNo={mapHoverSeqNo}
                onHoverSeqNo={handleMapHover}
              />
            </div>
          ) : (
            <div className="px-5 pb-5">
              <PanelError
                message={trackError ?? "不明なエラー"}
                onRetry={() => {
                  void trackQuery.refetch();
                }}
              />
            </div>
          )}
        </section>
      )}

      {/* Splits: table + per-split narrative from the split analyst */}
      {hasSplits && (
        <section
          id="section-splits"
          className={`scroll-mt-20 ${CARD_CLASS}`}
        >
          <h2 className="mb-3 font-display text-base font-semibold text-ink">
            スプリット
          </h2>
          {splits.length > 0 && (
            // Six numeric columns overflow a ~360px screen: the wrapper scrolls
            // the table instead of letting the page scroll sideways (#912).
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs tracking-wide text-slate-500 uppercase">
                    <th scope="col" className="px-2 py-2 text-left font-medium">
                      #
                    </th>
                    <th
                      scope="col"
                      className="px-2 py-2 text-right font-medium"
                    >
                      距離
                    </th>
                    <th
                      scope="col"
                      className="px-2 py-2 text-right font-medium"
                    >
                      ペース
                    </th>
                    <th
                      scope="col"
                      className="px-2 py-2 text-right font-medium"
                    >
                      心拍
                    </th>
                    <th
                      scope="col"
                      className="px-2 py-2 text-right font-medium"
                    >
                      ケイデンス
                    </th>
                    <th
                      scope="col"
                      className="px-2 py-2 text-right font-medium"
                    >
                      パワー
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-numeric text-[15px]">
                  {splits.map((split) => {
                    // Fragment rows keep their numbers but never draw a bar:
                    // their pace is an artifact of a manual lap press.
                    const isFragment =
                      typeof split.distance !== "number" ||
                      split.distance < BAR_MIN_SPLIT_KM;
                    return (
                      <tr key={split.split_index} className="hover:bg-slate-50">
                        <td className="px-2 py-2 text-left tabular-nums text-slate-500">
                          {split.split_index}
                        </td>
                        <td className="px-2 py-2 text-right tabular-nums">
                          {formatDistance(split.distance)}
                        </td>
                        <BarCell
                          widthPct={
                            isFragment
                              ? null
                              : barWidthPct(
                                  split.pace_seconds_per_km,
                                  paceScale,
                                  true,
                                )
                          }
                          color={METRIC_COLORS.speed}
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
                        >
                          {formatNumber(split.heart_rate, 0)}
                        </BarCell>
                        <td className="px-2 py-2 text-right tabular-nums">
                          {formatCadence(split.cadence)}
                        </td>
                        <td className="px-2 py-2 text-right tabular-nums">
                          {formatNumber(split.power, 0)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          <SplitNarrative section={sections?.split} />
        </section>
      )}

      {/* Phase evaluation timeline */}
      {sections?.phase && (
        <div id="section-phase" className="scroll-mt-20">
          <PhaseTimeline section={sections.phase} />
        </div>
      )}

      {/* Efficiency: structured form stats + analyst prose */}
      {sections?.efficiency && (
        <div id="section-efficiency" className="scroll-mt-20">
          <EfficiencyReport
            section={sections.efficiency}
            formEvaluations={detail.form_evaluations}
          />
        </div>
      )}

      {/* Environmental impact */}
      {sections?.environment && (
        <div id="section-environment" className="scroll-mt-20">
          <EnvironmentReport section={sections.environment} />
        </div>
      )}

      {/* Unknown section types degrade to key-value cards */}
      {sections &&
        unknownSectionTypes.map((type) => (
          <ReportCard key={type} title={type} section={sections[type]}>
            {(data) => <FallbackFields data={data} exclude={["metadata"]} />}
          </ReportCard>
        ))}
    </div>
  );
}
