import { Link } from "react-router-dom";
import EmptyState, { CliCommand } from "../../components/EmptyState";
import type { WeeklyReview, WeeklyReviewVerdict } from "../../types";

/** Local-date ISO string (YYYY-MM-DD) — avoids UTC shift from toISOString(). */
export function toIsoDate(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

const WEEKDAYS = ["日", "月", "火", "水", "木", "金", "土"];

/** "MM/DD (曜)" from a YYYY-MM-DD string; returns the input when unparseable. */
function formatDayLabel(isoDate: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate);
  if (match == null) {
    return isoDate;
  }
  const [, y, m, d] = match;
  const weekday =
    WEEKDAYS[new Date(Number(y), Number(m) - 1, Number(d)).getDay()];
  return `${m}/${d} (${weekday})`;
}

interface ThisWeekPlanProps {
  review: WeeklyReview | null;
  /** Injectable clock for tests. */
  today?: Date;
}

/**
 * "次の行動" card: the latest weekly review's day-by-day plan (coach verdict
 * table, today's row highlighted) plus its top-2 recommendations. Falls back
 * to the raw Garmin schedule when the review has no verdict rows.
 */
export default function ThisWeekPlan({
  review,
  today = new Date(),
}: ThisWeekPlanProps) {
  if (review?.review_data == null) {
    return (
      <section
        aria-label="今週のプランと次の行動"
        className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
      >
        <h2 className="mb-2 font-display text-base font-semibold text-ink">
          今週のプランと次の行動
        </h2>
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

  const data = review.review_data;
  const todayIso = toIsoDate(today);
  const isCurrentWeek =
    review.week_start_date <= todayIso && todayIso <= review.week_end_date;

  // The coach verdict table is the primary plan view; fall back to the raw
  // Garmin schedule when a review predates the verdict format.
  const rows: WeeklyReviewVerdict[] =
    data.verdict != null && data.verdict.length > 0
      ? data.verdict
      : (data.garmin_next_week ?? []).map((item) => ({
          date: item.date,
          session: item.title,
        }));

  const recommendations = (data.recommendations ?? []).slice(0, 2);

  return (
    <section
      aria-label="今週のプランと次の行動"
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-base font-semibold text-ink">
          {isCurrentWeek ? "今週のプラン" : "直近レビューのプラン"}
        </h2>
        <span className="font-numeric text-xs tabular-nums text-slate-400">
          {review.week_start_date} 〜 {review.week_end_date}
        </span>
      </div>

      {rows.length > 0 ? (
        <ul className="divide-y divide-slate-100">
          {rows.map((row, i) => {
            const isToday = row.date === todayIso;
            return (
              <li
                // Rows are positional; verdicts carry no stable id.
                // eslint-disable-next-line react/no-array-index-key
                key={i}
                className={`flex items-start gap-3 px-2 py-2 ${
                  isToday ? "rounded-lg bg-signal/5 ring-1 ring-signal/20" : ""
                }`}
              >
                <span className="w-20 shrink-0 pt-0.5 font-numeric text-sm tabular-nums text-slate-500">
                  {row.date != null ? formatDayLabel(row.date) : "—"}
                </span>
                <span aria-hidden="true" className="shrink-0 pt-0.5 text-sm">
                  {row.rating ?? "・"}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-2 text-sm font-medium text-slate-800">
                    {row.session ?? "-"}
                    {isToday && (
                      <span className="rounded-full bg-signal/15 px-2 py-0.5 text-[10px] font-bold text-signal">
                        今日
                      </span>
                    )}
                  </span>
                  {row.comment != null && row.comment !== "" && (
                    <span className="mt-0.5 block text-xs leading-relaxed text-slate-500">
                      {row.comment}
                    </span>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      ) : (
        <EmptyState message="この週のプラン明細がありません" />
      )}

      {recommendations.length > 0 && (
        <div className="mt-4 space-y-2 border-t border-slate-100 pt-4">
          <h3 className="text-xs font-semibold tracking-[0.2em] text-slate-400 uppercase">
            Next Actions
          </h3>
          {recommendations.map((rec, i) => (
            <p
              // eslint-disable-next-line react/no-array-index-key
              key={i}
              className="rounded-lg border-l-4 border-signal bg-slate-50 px-3 py-2 text-sm leading-relaxed text-slate-700"
            >
              {rec}
            </p>
          ))}
        </div>
      )}

      <div className="mt-4 text-right">
        <Link
          to={`/weekly-reviews/${review.week_start_date}`}
          className="text-sm font-medium text-status-info hover:underline"
        >
          レビュー全文 →
        </Link>
      </div>
    </section>
  );
}
