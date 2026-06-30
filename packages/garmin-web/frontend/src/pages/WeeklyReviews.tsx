import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import EmptyState, { CliCommand } from "../components/EmptyState";
import SectionHeading from "../components/SectionHeading";
import { fetchWeeklyReviews } from "../api/client";
import type { WeeklyReview } from "../types";

/** Count verdict entries with a given emoji rating. */
export function countRating(review: WeeklyReview, rating: string): number {
  const verdict = review.review_data?.verdict ?? [];
  return verdict.filter((v) => v.rating === rating).length;
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
  const [reviews, setReviews] = useState<WeeklyReview[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetchWeeklyReviews()
      .then((data) => {
        if (!cancelled) {
          setReviews(data);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-3 py-16 text-sm text-slate-500">
        <span
          aria-hidden="true"
          className="h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-ink"
        />
        読み込み中...
      </div>
    );
  }
  if (error) {
    return (
      <p
        role="alert"
        className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
      >
        エラー: {error}
      </p>
    );
  }
  if (reviews == null) {
    return null;
  }

  return (
    <div className="stagger-in space-y-6">
      <SectionHeading eyebrow="Weekly Review" title="週次レビュー" />

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
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
                      <span className="font-numeric text-xs tabular-nums text-slate-500">
                        <span className="mr-2">✅ {greenCount}</span>
                        <span className="mr-2">🟡 {yellowCount}</span>
                        <span>🔴 {redCount}</span>
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
