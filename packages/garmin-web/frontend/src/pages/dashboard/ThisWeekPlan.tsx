import { Link } from "react-router-dom";
import EmptyState, { CliCommand } from "../../components/EmptyState";
import StatusBadge from "../../components/StatusBadge";
import {
  sessionLabel,
  statusLabel,
  statusTone,
  targetSummary,
} from "../../components/plan/DayCell";
import type { PlanWeek, WeeklyReview } from "../../types";
import { ratingMeta } from "../../utils/verdictRating";
import { CARD_CLASS } from "../../components/Card";
import { formatDate, toIsoDate } from "../../utils/format";
import { formatDayLabel } from "../../utils/week";

/** One line of the plan list, whatever it was derived from. */
interface PlanRow {
  date?: string;
  /** The session name ("ロング 22km", "Tempo"). */
  label: string;
  /** Prescription lifecycle status, rendered as a chip. */
  status?: string;
  /** Coach verdict emoji, rendered as a named image. */
  rating?: string;
  /** Target summary or the coach's comment. */
  detail?: string;
}

/** Structured prescriptions win over the coach verdict; both beat Garmin. */
function planRows(week: PlanWeek | null, review: WeeklyReview | null): PlanRow[] {
  const prescriptions = (week?.days ?? []).flatMap((day) =>
    day.prescriptions.map((prescription) => ({
      date: day.date,
      label: prescription.title || sessionLabel(prescription.session_type),
      status: prescription.status,
      detail: targetSummary(prescription),
    })),
  );
  if (prescriptions.length > 0) {
    return prescriptions;
  }

  const data = review?.review_data;
  const verdict = data?.verdict ?? [];
  if (verdict.length > 0) {
    return verdict.map((row) => ({
      date: row.date,
      label: row.session ?? "-",
      rating: row.rating,
      detail: row.comment,
    }));
  }
  return (data?.garmin_next_week ?? []).map((item) => ({
    date: item.date,
    label: item.title ?? "-",
  }));
}

interface ThisWeekPlanProps {
  review: WeeklyReview | null;
  /** The current week of the month plan, when it has prescriptions (#983). */
  week?: PlanWeek | null;
  /** Injectable clock for tests. */
  today?: Date;
}

/**
 * "次の行動" card: the week's day-by-day plan (today's row highlighted) plus
 * the latest review's top-2 recommendations.
 *
 * The structured prescriptions are the plan when the week has them (#983) —
 * they carry the target and the lifecycle status, which the prose verdict
 * cannot. A week that predates them falls back to the coach verdict table, and
 * a review that predates *that* falls back to the raw Garmin schedule.
 */
export default function ThisWeekPlan({
  review,
  week = null,
  today = new Date(),
}: ThisWeekPlanProps) {
  const rows = planRows(week, review);

  if (review?.review_data == null && rows.length === 0) {
    return (
      <section aria-label="今週のプランと次の行動" className={CARD_CLASS}>
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

  const todayIso = toIsoDate(today);
  const weekStart = week?.week_start ?? review?.week_start_date ?? null;
  const weekEnd = week?.week_end ?? review?.week_end_date ?? null;
  const isCurrentWeek =
    weekStart != null &&
    weekEnd != null &&
    weekStart <= todayIso &&
    todayIso <= weekEnd;
  const recommendations = (review?.review_data?.recommendations ?? []).slice(
    0,
    2,
  );

  return (
    <section aria-label="今週のプランと次の行動" className={CARD_CLASS}>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-base font-semibold text-ink">
          {isCurrentWeek ? "今週のプラン" : "直近レビューのプラン"}
        </h2>
        {weekStart != null && weekEnd != null && (
          <span className="font-numeric text-xs tabular-nums text-slate-500">
            {formatDate(weekStart)} 〜 {formatDate(weekEnd)}
          </span>
        )}
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
                {row.rating != null ? (
                  // The rating is the row's verdict, so it needs a name a
                  // screen reader can use — "large red circle" is not one
                  // (#912). Rows without a rating keep the decorative bullet.
                  <span
                    role="img"
                    aria-label={ratingMeta(row.rating).label}
                    className="shrink-0 pt-0.5 text-sm"
                  >
                    {row.rating}
                  </span>
                ) : row.status != null ? (
                  <span className="shrink-0 pt-0.5">
                    <StatusBadge tone={statusTone(row.status)}>
                      {statusLabel(row.status)}
                    </StatusBadge>
                  </span>
                ) : (
                  <span aria-hidden="true" className="shrink-0 pt-0.5 text-sm">
                    ・
                  </span>
                )}
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-2 text-sm font-medium text-slate-800">
                    {row.label}
                    {isToday && (
                      <span className="rounded-full bg-signal/15 px-2 py-0.5 text-[10px] font-bold text-signal-ink">
                        今日
                      </span>
                    )}
                  </span>
                  {row.detail != null && row.detail !== "" && (
                    <span className="mt-0.5 block text-xs leading-relaxed text-slate-500">
                      {row.detail}
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
          <h3 className="text-xs font-semibold tracking-[0.2em] text-slate-500 uppercase">
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

      {weekStart != null && (
        <div className="mt-4 text-right">
          <Link
            to={`/weekly-reviews/${weekStart}`}
            className="text-sm font-medium text-status-info hover:underline"
          >
            レビュー全文 →
          </Link>
        </div>
      )}
    </section>
  );
}
