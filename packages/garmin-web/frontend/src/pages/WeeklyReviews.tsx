import { Link } from "react-router-dom";
import EmptyState, { CliCommand } from "../components/EmptyState";
import SectionHeading from "../components/SectionHeading";
import { CARD_CLASS } from "../components/Card";
import { PageError, PageLoading } from "../components/PageState";
import { useWeeklyReviews } from "../api/hooks";
import { usePageTitle } from "../hooks/usePageTitle";
import type { WeeklyReview } from "../types";
import { ratingMarks } from "../utils/verdictRating";

/** Count verdict entries with a given emoji rating. */
export function countRating(review: WeeklyReview, rating: string): number {
  const verdict = review.review_data?.verdict ?? [];
  return verdict.filter((v) => v.rating === rating).length;
}

/** "良好 4件 注意 2件 要改善 1件" — the emoji tally in words. */
function ratingSummary(
  green: number,
  yellow: number,
  red: number,
): string {
  const counts = [green, yellow, red];
  return ratingMarks()
    .map(({ label }, i) => `${label} ${counts[i]}件`)
    .join(" ");
}

/** Short excerpt of the overall text (first ~60 chars). */
export function overallExcerpt(review: WeeklyReview): string {
  const overall = review.review_data?.overall;
  if (overall == null || overall === "") {
    return "-";
  }
  return overall.length > 60 ? `${overall.slice(0, 60)}…` : overall;
}

export default function WeeklyReviews() {
  const { data, isPending, error, refetch } = useWeeklyReviews();
  // A resolved-but-absent list reads the same as an empty one; it used to
  // return null instead, rendering a white page with no explanation (#914).
  const reviews = data ?? [];
  usePageTitle("週次レビュー");

  if (isPending) {
    return <PageLoading />;
  }
  if (error) {
    return <PageError error={error} onRetry={() => void refetch()} />;
  }

  return (
    <div className="stagger-in space-y-6">
      {/* The list left the nav for /plan (#983), so it states its way back. */}
      <div className="flex items-start justify-between gap-3">
        <SectionHeading eyebrow="Weekly Review" title="週次レビュー" />
        <Link
          to="/plan"
          className="text-sm font-medium text-slate-600 hover:text-ink"
        >
          ← 計画へ
        </Link>
      </div>

      <section className={CARD_CLASS}>
        {reviews.length > 0 ? (
          <ul className="divide-y divide-slate-100">
            {reviews.map((review) => {
              const redCount = countRating(review, "🔴");
              const yellowCount = countRating(review, "🟡");
              const greenCount = countRating(review, "✅");
              return (
                <li key={review.week_start_date}>
                  <Link
                    to={`/weekly-reviews/${review.week_start_date}`}
                    className="-mx-2 flex flex-col gap-1 rounded-lg px-2 py-3 transition-colors hover:bg-slate-50"
                  >
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="font-display text-sm font-semibold text-ink">
                        {review.week_start_date} 〜 {review.week_end_date}
                      </span>
                      {/*
                       * The emoji tally is a visual scan aid; the words behind
                       * it are what the link announces (#912), so the counts
                       * are not read out as three unnamed circles.
                       */}
                      <span className="font-numeric text-xs tabular-nums text-slate-500">
                        <span aria-hidden="true" className="mr-2">
                          ✅ {greenCount}
                        </span>
                        <span aria-hidden="true" className="mr-2">
                          🟡 {yellowCount}
                        </span>
                        <span aria-hidden="true">🔴 {redCount}</span>
                        <span className="sr-only">
                          {ratingSummary(greenCount, yellowCount, redCount)}
                        </span>
                      </span>
                    </div>
                    <p className="text-sm text-slate-600">
                      {overallExcerpt(review)}
                    </p>
                  </Link>
                </li>
              );
            })}
          </ul>
        ) : (
          <EmptyState
            message="週次レビューが登録されていません"
            hint={
              <>
                CLI <CliCommand>/weekly-review</CliCommand> で作成できます
              </>
            }
          />
        )}
      </section>
    </div>
  );
}
