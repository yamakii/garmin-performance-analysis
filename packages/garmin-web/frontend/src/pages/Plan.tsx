import { Link, useSearchParams } from "react-router-dom";
import { useMonthPlan } from "../api/hooks";
import { CARD_CLASS } from "../components/Card";
import QueryBoundary from "../components/QueryBoundary";
import SectionHeading from "../components/SectionHeading";
import AdherenceChip from "../components/plan/AdherenceChip";
import BlockBands from "../components/plan/BlockBands";
import MonthGrid from "../components/plan/MonthGrid";
import { usePageTitle } from "../hooks/usePageTitle";
import { toIsoDate } from "../utils/format";
import { formatMonthLabel, shiftMonth } from "../utils/week";

const MONTH_RE = /^\d{4}-(0[1-9]|1[0-2])$/;

/** The month a date falls in, as `YYYY-MM`. */
function monthOf(date: Date): string {
  return toIsoDate(date).slice(0, 7);
}

const NAV_BUTTON =
  "rounded-md border border-slate-200 bg-white px-2.5 py-1 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-ink";

/**
 * "この1ヶ月どう積むか?" — the plan page (#983).
 *
 * Rows are weeks and columns run from the athlete's configured week start, so
 * with a Monday start the Sunday long run is the last column and the shape of
 * a training week is visible at a glance. Above the grid sit the training
 * blocks the month falls inside; each row states its adherence and links to
 * that week's review, which is where the prose lives.
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

  function goToMonth(next: string) {
    const params = new URLSearchParams(searchParams);
    params.set("month", next);
    setSearchParams(params);
  }

  return (
    <div className="stagger-in space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <SectionHeading eyebrow="Plan" title="計画" />
        <Link
          to="/weekly-reviews"
          className="text-sm font-medium text-slate-600 hover:text-ink"
        >
          週次レビュー一覧 →
        </Link>
      </div>

      <div className="flex items-center gap-3">
        <button
          type="button"
          aria-label="前の月"
          onClick={() => goToMonth(shiftMonth(month, -1))}
          className={NAV_BUTTON}
        >
          ‹
        </button>
        <h2 className="font-display text-lg font-semibold text-ink">
          {formatMonthLabel(month)}
        </h2>
        <button
          type="button"
          aria-label="次の月"
          onClick={() => goToMonth(shiftMonth(month, 1))}
          className={NAV_BUTTON}
        >
          ›
        </button>
      </div>

      <QueryBoundary label="月間プラン" query={monthPlanQuery}>
        {(plan) => (
          <div className="space-y-4">
            <BlockBands blocks={plan.blocks} />
            <section className={CARD_CLASS}>
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h3 className="font-display text-base font-semibold text-ink">
                  週ごとの計画と実績
                </h3>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-slate-600">今月の実施</span>
                  <AdherenceChip adherence={plan.adherence} />
                </div>
              </div>
              <MonthGrid plan={plan} />
            </section>
          </div>
        )}
      </QueryBoundary>
    </div>
  );
}
