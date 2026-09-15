import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  useActivities,
  useGoal,
  useMonthPlan,
  useRaceReadiness,
  useRecoveryStatus,
  useRecoveryTrend,
  useTrainingLoad,
  useWeeklyReviews,
  useWellnessBaselineDeviation,
} from "../api/hooks";
import CoachNote from "../components/CoachNote";
import EmptyState, { CliCommand } from "../components/EmptyState";
import QueryBoundary, { type QueryLike } from "../components/QueryBoundary";
import SectionHeading from "../components/SectionHeading";
import VerdictLine from "../components/VerdictLine";
import VitalsRow, { type VitalItem } from "../components/VitalsRow";
import { phaseLabel } from "../components/plan/BlockBands";
import { usePageTitle } from "../hooks/usePageTitle";
import type {
  AcwrStatus,
  AcwrTrend,
  MetricBaseline,
  MonthPlan,
  PlanWeek,
  RecoveryStatus,
  RecoveryTrend,
  WeeklyReview,
  WellnessBaselineDeviation,
} from "../types";
import { formatDateLabel, toIsoDate } from "../utils/format";
import { formatNumber } from "../utils/formatNumber";
import { homeVerdict, todayPrescription } from "../utils/verdict";
import ProgressRow from "./dashboard/ProgressRow";
import WeekStrip from "./dashboard/WeekStrip";

/** The three endpoints behind the vitals row, as one block's worth of data. */
interface VitalsData {
  load: AcwrTrend | null;
  recovery: RecoveryTrend | null;
  status: RecoveryStatus | null;
}

/** The plan (required) and the latest review (supplementary) of 今週. */
interface WeekData {
  plan: MonthPlan | null;
  review: WeeklyReview | null;
}

const ACWR_LABELS: Record<AcwrStatus, string> = {
  undertraining: "負荷不足",
  optimal: "最適",
  caution: "注意",
  high_risk: "高リスク",
  insufficient_data: "データ不足",
};

/** ACWR status → note tone; only 注意 and 高リスク get a colour. */
const ACWR_TONE: Partial<Record<AcwrStatus, "warn" | "bad">> = {
  caution: "warn",
  high_risk: "bad",
};

/** Japanese name per baseline metric, used when a reason omits it. */
const METRIC_NAMES = {
  hrv: "HRV",
  rhr: "安静時心拍",
  readiness: "準備度",
} as const;

/** "55–65" — the personal baseline band (mean ± 1σ) of a metric. */
function baselineBand(metric: MetricBaseline | null): string | null {
  if (metric?.mean == null || metric.std == null) {
    return null;
  }
  return `${formatNumber(metric.mean - metric.std, 0)}–${formatNumber(
    metric.mean + metric.std,
    0,
  )}`;
}

/** UTC epoch of a YYYY-MM-DD day; null when it is not a calendar day. */
function utcDay(iso: string | null): number | null {
  const match = iso != null ? /^(\d{4})-(\d{2})-(\d{2})/.exec(iso) : null;
  return match == null
    ? null
    : Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
}

/** "09/07" — the short day label used in the week's caption. */
function shortDay(iso: string): string {
  return formatDateLabel(iso).slice(0, 5);
}

/**
 * "09/07 – 09/13 · ビルド 3/7週 · 計画 38km" — where the week sits in the
 * block and what it asks for. The phase part is dropped when no block spans
 * the week, so an unplanned month still gets its dates.
 */
function weekCaption(plan: MonthPlan | null, week: PlanWeek): string {
  const parts = [`${shortDay(week.week_start)} – ${shortDay(week.week_end)}`];

  const block = (plan?.blocks ?? []).find((candidate) => {
    const start = utcDay(candidate.start_date);
    const end = utcDay(candidate.end_date);
    const weekStart = utcDay(week.week_start);
    const weekEnd = utcDay(week.week_end);
    return (
      start != null &&
      end != null &&
      weekStart != null &&
      weekEnd != null &&
      start <= weekEnd &&
      weekStart <= end
    );
  });
  const blockStart = utcDay(block?.start_date ?? null);
  const blockEnd = utcDay(block?.end_date ?? null);
  const weekStart = utcDay(week.week_start);
  if (block != null && blockStart != null && blockEnd != null && weekStart != null) {
    const index = Math.max(
      1,
      Math.floor((weekStart - blockStart) / 604_800_000) + 1,
    );
    const total = Math.ceil((blockEnd - blockStart) / 86_400_000 / 7 + 1 / 7);
    parts.push(`${phaseLabel(block.phase)} ${index}/${total}週`);
  }

  const planned = week.days
    .flatMap((day) => day.prescriptions)
    .reduce((sum, prescription) => sum + (prescription.target_km ?? 0), 0);
  if (planned > 0) {
    parts.push(`計画 ${formatNumber(planned, 1)}km`);
  }
  return parts.join(" · ");
}

/**
 * The verdict's rationale: the reader's leading reason, plus the baseline
 * metric that is out of band when the reason has not already named it.
 */
function verdictLead(
  status: RecoveryStatus,
  baseline: WellnessBaselineDeviation | null,
): ReactNode {
  const reason = status.reasons[0] ?? null;
  const adverse = (["hrv", "rhr", "readiness"] as const).find(
    (metric) => baseline?.[metric].adverse === true,
  );
  const name = adverse != null ? METRIC_NAMES[adverse] : null;
  const unmentioned = name != null && !(reason ?? "").includes(name);
  if (reason == null && !unmentioned) {
    return null;
  }
  return (
    <>
      {reason}
      {unmentioned && (
        <span className="font-bold text-status-warn">
          {reason != null ? " " : ""}
          {name}が基準外
        </span>
      )}
    </>
  );
}

/** The four numbers of the morning, each linked to the page that owns it. */
function vitalsItems(
  { load, recovery, status }: VitalsData,
  baseline: WellnessBaselineDeviation | null,
): VitalItem[] {
  const hrv = recovery?.hrv ?? null;
  const rhr = recovery?.rhr ?? null;
  const acwr = load?.current ?? null;
  const weeks = load?.trend.weeks ?? [];
  const lastWeek = weeks[weeks.length - 1] ?? null;

  const hrvBelow = hrv?.hrv_below_baseline_days ?? 0;
  const hrvBand = baselineBand(baseline?.hrv ?? null);
  const rhrBaseline = baseline?.rhr ?? null;
  const rhrBand = baselineBand(rhrBaseline);
  const rhrDelta =
    rhrBaseline?.today != null && rhrBaseline.mean != null
      ? rhrBaseline.today - rhrBaseline.mean
      : null;

  return [
    {
      label: "HRV 夜間",
      value: hrv?.latest_ms != null ? formatNumber(hrv.latest_ms, 0) : "—",
      unit: "ms",
      note:
        hrv?.under_recovery === true || hrvBelow > 0
          ? `基準割れ ${hrvBelow}日連続`
          : hrvBand != null
            ? `基準内 · ${hrvBand}`
            : "7日平均 —",
      noteTone:
        hrv?.under_recovery === true || hrvBelow > 0 ? "warn" : "muted",
      to: "/condition#recovery",
    },
    {
      label: "安静時心拍",
      value: rhr?.median_7d != null ? formatNumber(rhr.median_7d, 0) : "—",
      unit: "bpm",
      note:
        rhrBaseline?.adverse === true && rhrDelta != null
          ? `${rhrDelta > 0 ? "+" : ""}${formatNumber(rhrDelta, 0)} · 基準外`
          : rhrBand != null
            ? `基準 ${rhrBand}`
            : "7日中央値",
      noteTone: rhrBaseline?.adverse === true ? "warn" : "muted",
      to: "/condition#recovery",
    },
    {
      label: "睡眠 / 準備度",
      value: (
        <>
          {status?.sleep_score != null
            ? formatNumber(status.sleep_score, 0)
            : "—"}
          <span className="mx-1.5 text-[13px] text-ink-muted">/</span>
          {status?.training_readiness != null
            ? formatNumber(status.training_readiness, 0)
            : "—"}
        </>
      ),
      note: `Body Battery ${
        status?.body_battery_high != null
          ? formatNumber(status.body_battery_high, 0)
          : "—"
      }`,
      to: "/condition#today",
    },
    {
      label: "負荷 ACWR",
      value:
        acwr?.acwr != null && acwr.status !== "insufficient_data"
          ? formatNumber(acwr.acwr, 2)
          : "—",
      note:
        acwr != null
          ? `${ACWR_LABELS[acwr.status]}${
              lastWeek != null ? ` · 週 ${formatNumber(lastWeek.load_km, 1)}km` : ""
            }`
          : "週間負荷 —",
      noteTone: acwr != null ? (ACWR_TONE[acwr.status] ?? "muted") : "muted",
      to: "/condition#training-load",
    },
  ];
}

/**
 * Home: the morning brief. It reads as one page top-down — the verdict and
 * today's session, the four numbers behind it, the week it sits in, and how
 * far the season has come.
 *
 * Every block keeps its own `QueryBoundary` (#895): one broken endpoint
 * degrades into a retryable alert in place of that block instead of replacing
 * the brief with a banner. Supplementary readings (the wellness baseline, the
 * race readiness and the goal) enrich a block rather than being one, so they
 * degrade away silently.
 */
export default function Dashboard() {
  usePageTitle("ホーム");
  const recoveryStatusQuery = useRecoveryStatus();
  const loadQuery = useTrainingLoad();
  const recoveryQuery = useRecoveryTrend();
  const monthPlanQuery = useMonthPlan();
  const reviewsQuery = useWeeklyReviews(1);
  const activitiesQuery = useActivities();
  const baselineQuery = useWellnessBaselineDeviation();
  const readinessQuery = useRaceReadiness();
  const goalQuery = useGoal();

  const todayIso = toIsoDate(new Date());
  const baseline = baselineQuery.data ?? null;
  const weeks = monthPlanQuery.data?.weeks;
  const currentWeek = Array.isArray(weeks)
    ? (weeks.find(
        (week) => week.week_start <= todayIso && todayIso <= week.week_end,
      ) ?? null)
    : null;

  // The vitals row reads as one block, so it gets one boundary: it shows the
  // first failure (retrying all three) and otherwise renders as soon as any
  // reading lands, letting the rest fill in behind their placeholders.
  const vitalsQuery: QueryLike<VitalsData> = {
    data:
      loadQuery.data === undefined &&
      recoveryQuery.data === undefined &&
      recoveryStatusQuery.data === undefined
        ? undefined
        : {
            load: loadQuery.data ?? null,
            recovery: recoveryQuery.data ?? null,
            status: recoveryStatusQuery.data ?? null,
          },
    error: loadQuery.error ?? recoveryQuery.error ?? recoveryStatusQuery.error,
    refetch: () => {
      loadQuery.refetch();
      recoveryQuery.refetch();
      recoveryStatusQuery.refetch();
    },
  };

  // The plan carries the week; the review only adds the coach's note, so a
  // missing review must not fail the block.
  const weekQuery: QueryLike<WeekData> = {
    data:
      monthPlanQuery.data === undefined && reviewsQuery.data === undefined
        ? undefined
        : {
            plan: monthPlanQuery.data ?? null,
            review: reviewsQuery.data?.[0] ?? null,
          },
    error: monthPlanQuery.error ?? reviewsQuery.error,
    refetch: () => {
      monthPlanQuery.refetch();
      reviewsQuery.refetch();
    },
  };

  return (
    <div className="flex flex-col gap-12">
      {/* ① 判定: 今日どう動くか */}
      <QueryBoundary label="今日の判定" query={recoveryStatusQuery}>
        {(status) => {
          const verdict = homeVerdict(
            status,
            todayPrescription(currentWeek, todayIso),
          );
          return (
            <VerdictLine
              verdict={verdict.verdict}
              verdictTone={verdict.tone}
              rest={verdict.rest}
              lead={verdictLead(status, baseline)}
              actions={
                <>
                  <Link
                    to="/plan"
                    className="inline-block rounded-sm bg-ink px-4 py-2.5 text-sm font-bold text-paper hover:no-underline"
                  >
                    今日のメニュー詳細
                  </Link>
                  <Link to="/condition" className="font-mono text-sm">
                    判定の根拠 → コンディション
                  </Link>
                </>
              }
            />
          );
        }}
      </QueryBoundary>

      {/* ② 今朝の数値: 判定を支える4つの読み */}
      <QueryBoundary label="今朝の数値" query={vitalsQuery}>
        {(vitals) => (
          <VitalsRow
            ariaLabel="今朝の数値"
            items={vitalsItems(vitals, baseline)}
          />
        )}
      </QueryBoundary>

      {/* ③ 今週: 7日のかたちとコーチのひとこと */}
      <QueryBoundary label="今週" query={weekQuery}>
        {({ plan, review }) => {
          const recommendation =
            review?.review_data?.recommendations?.[0] ?? null;
          if (currentWeek == null && recommendation == null) {
            return (
              <section aria-label="今週" className="flex flex-col gap-4">
                <SectionHeading as="h2" title="今週" />
                <EmptyState
                  message="週次レビューがまだありません"
                  hint={
                    <>
                      CLI <CliCommand>/weekly-review</CliCommand> で生成できます
                    </>
                  }
                />
              </section>
            );
          }
          return (
            <section aria-label="今週" className="flex flex-col gap-4">
              <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                <div className="min-w-0 grow">
                  <SectionHeading
                    as="h2"
                    title="今週"
                    note={
                      currentWeek != null
                        ? weekCaption(plan, currentWeek)
                        : undefined
                    }
                  />
                </div>
                <Link to="/plan" className="font-mono text-[13px]">
                  月間計画 →
                </Link>
              </div>

              {currentWeek != null && (
                <WeekStrip
                  week={currentWeek}
                  days={currentWeek.days.map((day) => day.date)}
                  today={todayIso}
                />
              )}

              {recommendation != null && review != null && (
                <CoachNote
                  source={{
                    label: `週次レビュー ${shortDay(review.week_start_date)} →`,
                    to: `/weekly-reviews/${review.week_start_date}`,
                  }}
                >
                  {recommendation}
                </CoachNote>
              )}
            </section>
          );
        }}
      </QueryBoundary>

      {/* ④ 進捗: レースまでの距離と前回のラン */}
      <QueryBoundary label="進捗" query={activitiesQuery}>
        {(activities) => (
          <ProgressRow
            readiness={readinessQuery.data ?? null}
            goals={goalQuery.data?.goals ?? null}
            activities={activities}
          />
        )}
      </QueryBoundary>
    </div>
  );
}
