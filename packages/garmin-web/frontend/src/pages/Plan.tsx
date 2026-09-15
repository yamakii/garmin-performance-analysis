import type { JSX, ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMonthPlan, useWeeklyReviews } from "../api/hooks";
import CoachNote from "../components/CoachNote";
import QueryBoundary from "../components/QueryBoundary";
import BlockBands from "../components/plan/BlockBands";
import MonthGrid from "../components/plan/MonthGrid";
import { usePageTitle } from "../hooks/usePageTitle";
import { toIsoDate } from "../utils/format";
import { formatNumber } from "../utils/formatNumber";
import {
  type MonthSummary,
  monthSentence,
  monthSummary,
} from "../utils/planSummary";
import {
  formatMonthLabel,
  shiftMonth,
  weekRowsForMonth,
} from "../utils/week";

const MONTH_RE = /^\d{4}-(0[1-9]|1[0-2])$/;

/** The month a date falls in, as `YYYY-MM`. */
function monthOf(date: Date): string {
  return toIsoDate(date).slice(0, 7);
}

/** "8月" — the neighbouring month on a navigation button. */
function shortMonthLabel(month: string): string {
  const match = /^\d{4}-(\d{2})$/.exec(month);
  return match != null ? `${Number(match[1])}月` : month;
}

const NAV_BUTTON =
  "rounded-sm border border-ink px-3 py-[7px] text-[13px] font-bold text-ink";

/** One figure of the month's summary row. */
function Figure({
  label,
  value,
  note,
}: {
  label: string;
  value: ReactNode;
  note?: string;
}): JSX.Element {
  return (
    <div className="flex flex-col gap-1 py-3 pr-4">
      <dt className="font-mono text-xs text-ink-muted">{label}</dt>
      <dd className="font-mono text-[18px] leading-none font-medium text-ink">
        {value}
        {note != null && (
          <span className="ml-1.5 text-xs font-normal text-ink-muted">
            {note}
          </span>
        )}
      </dd>
    </div>
  );
}

/** 計画 / 実績 / 実施率 / ポイント練 — the month in four numbers. */
function MonthFigures({ summary }: { summary: MonthSummary }): JSX.Element {
  return (
    <dl className="grid grid-cols-2 border-t border-ink border-b border-hairline md:grid-cols-4">
      <Figure label="計画" value={`${formatNumber(summary.plannedKm, 1)}km`} />
      <Figure label="実績" value={`${formatNumber(summary.actualKm, 1)}km`} />
      <Figure
        label="実施率"
        value={`${summary.done}/${summary.resolved}`}
        note="確定分"
      />
      <Figure
        label="ポイント練"
        value={
          summary.qualityPerWeek != null ? `週${summary.qualityPerWeek}` : "—"
        }
      />
    </dl>
  );
}

/**
 * "この1ヶ月どう積むか?" — the plan page (#983, redesigned in #1119).
 *
 * The month opens with one sentence (where it sits in the block, how much of
 * it happened) and its four numbers; below them the training blocks are drawn
 * as bands over the same columns the grid uses, so a phase change lands on a
 * calendar day instead of being a date range to decode. Rows are weeks and
 * columns run from the athlete's week start, so with a Monday start the Sunday
 * long run is the last column and the shape of a training week is visible at a
 * glance. The prose lives in the weekly review each row links to; the last
 * word on the page is the coach's, quoted from the latest one.
 *
 * The month lives in the URL (`?month=2026-09`), so a month is bookmarkable
 * and survives reload and back-navigation — the same rule `/activities` uses
 * for its filters (#893).
 */
export default function Plan() {
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get("month");
  const month =
    requested != null && MONTH_RE.test(requested)
      ? requested
      : monthOf(new Date());
  usePageTitle(`計画 ${formatMonthLabel(month)}`);
  const monthPlanQuery = useMonthPlan(month);
  const reviewsQuery = useWeeklyReviews(1);
  const todayIso = toIsoDate(new Date());

  function goToMonth(next: string) {
    const params = new URLSearchParams(searchParams);
    params.set("month", next);
    setSearchParams(params);
  }

  const previous = shiftMonth(month, -1);
  const next = shiftMonth(month, 1);
  const review = reviewsQuery.data?.[0] ?? null;
  const recommendation = review?.review_data?.recommendations?.[0] ?? null;

  return (
    <div className="flex flex-col gap-8 md:-mx-10">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          aria-label="前の月"
          onClick={() => goToMonth(previous)}
          className={NAV_BUTTON}
        >
          ← {shortMonthLabel(previous)}
        </button>
        <h1 className="text-[28px] leading-tight font-bold text-ink">
          {formatMonthLabel(month)}
        </h1>
        <button
          type="button"
          aria-label="次の月"
          onClick={() => goToMonth(next)}
          className={NAV_BUTTON}
        >
          {shortMonthLabel(next)} →
        </button>
        <Link to="/weekly-reviews" className="ml-auto font-mono text-[13px]">
          週次レビュー一覧 →
        </Link>
      </div>

      <QueryBoundary label="月間プラン" query={monthPlanQuery}>
        {(plan) => {
          const summary = monthSummary(plan, todayIso);
          const sentence = monthSentence(summary);
          const days = weekRowsForMonth(plan.month, plan.week_start_day).flatMap(
            (row) => row.days,
          );
          return (
            <div className="flex flex-col gap-8">
              <div className="flex flex-col gap-4">
                <p className="max-w-[720px] text-xl leading-[1.5] text-ink-soft">
                  {sentence.lead !== "" && (
                    <span className="font-bold text-ink">{sentence.lead}</span>
                  )}
                  {sentence.rest}
                </p>
                <MonthFigures summary={summary} />
              </div>

              <div className="flex flex-col gap-2">
                <BlockBands blocks={plan.blocks} days={days} />
                <MonthGrid plan={plan} />
              </div>
            </div>
          );
        }}
      </QueryBoundary>

      {recommendation != null && review != null && (
        <CoachNote
          source={{
            label: "レビュー全文 →",
            to: `/weekly-reviews/${review.week_start_date}`,
          }}
        >
          {recommendation}
        </CoachNote>
      )}
    </div>
  );
}
