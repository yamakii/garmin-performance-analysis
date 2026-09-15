import { Link } from "react-router-dom";
import EmptyState, { CliCommand } from "../components/EmptyState";
import SectionHeading from "../components/SectionHeading";
import { CARD_CLASS } from "../components/Card";
import { PageError, PageLoading } from "../components/PageState";
import { useWeeklyReviews } from "../api/hooks";
import { usePageTitle } from "../hooks/usePageTitle";
import type { WeeklyReview } from "../types";
import { ratingMarks } from "../utils/verdictRating";

/** Count verdict entries with a given rating mark. */
export function countRating(review: WeeklyReview, rating: string): number {
  const verdict = review.review_data?.verdict ?? [];
  return verdict.filter((v) => v.rating === rating).length;
}

/**
 * The week's verdict counts, in `ratingMarks()` order (good → warn → bad).
 *
 * The marks come from {@link ratingMarks} rather than being written out here:
 * the agent stores an emoji in `rating`, but this page must not render one, so
 * the only emoji left in the flow is the key it matches on.
 */
export function ratingCounts(review: WeeklyReview): number[] {
  return ratingMarks().map(({ mark }) => countRating(review, mark));
}

/**
 * "良好 4 · 注意 2 · 要改善 1" — the tally in words (#1186).
 *
 * The page used to draw the three verdict emoji with the words hidden in an
 * `sr-only` span. A screen reader announced the red one as "large red circle",
 * and the row read as three unnamed counts to everyone else too, so the words
 * are the tally itself now (#912). Zero rows are dropped: what did not happen
 * is not worth a column.
 */
export function ratingTally(counts: number[]): string {
  const parts = ratingMarks()
    .map(({ label }, i) => (counts[i] > 0 ? `${label} ${counts[i]}` : null))
    .filter((part) => part != null);
  return parts.length > 0 ? parts.join(" · ") : "評価なし";
}

/**
 * Colour of the tally: the worst thing in the week decides it, so a week with
 * both 注意 and 要改善 reads as 要改善 rather than softening to the milder hue.
 */
export function tallyToneClass(counts: number[]): string {
  const [, warn = 0, bad = 0] = counts;
  if (bad > 0) {
    return "text-status-bad";
  }
  if (warn > 0) {
    return "text-status-warn";
  }
  return "text-ink-muted";
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
    <div className="space-y-6">
      {/* The list left the nav for /plan (#983), so it states its way back. */}
      <div className="flex items-start justify-between gap-3">
        <SectionHeading title="週次レビュー" />
        <Link
          to="/plan"
          className="text-sm font-medium text-ink-muted hover:text-ink"
        >
          ← 計画へ
        </Link>
      </div>

      <section className={CARD_CLASS}>
        {reviews.length > 0 ? (
          // Each row draws its own hairline, so the list adds no divider.
          <ul>
            {reviews.map((review) => {
              const counts = ratingCounts(review);
              return (
                <li key={review.week_start_date}>
                  <Link
                    to={`/weekly-reviews/${review.week_start_date}`}
                    className="flex flex-col gap-1 border-b border-hairline py-3 transition-colors hover:bg-surface"
                  >
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="font-mono text-[13px] font-semibold text-ink">
                        {review.week_start_date} 〜 {review.week_end_date}
                      </span>
                      <span
                        className={`font-mono text-xs ${tallyToneClass(counts)}`}
                      >
                        {ratingTally(counts)}
                      </span>
                    </div>
                    <p className="text-sm text-ink-muted">
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
