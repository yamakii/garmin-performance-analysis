import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { fetchWeeklyReview } from "../api/client";
import type { WeeklyReview } from "../types";

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="mb-3 font-display text-base font-semibold text-ink">
        {title}
      </h2>
      {children}
    </section>
  );
}

export default function WeeklyReviewDetail() {
  const { weekStart } = useParams<{ weekStart: string }>();
  const [review, setReview] = useState<WeeklyReview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (weekStart == null) {
      return;
    }
    let cancelled = false;
    setLoading(true);
    fetchWeeklyReview(weekStart)
      .then((data) => {
        if (!cancelled) {
          setReview(data);
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
  }, [weekStart]);

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
  if (review == null) {
    return null;
  }

  const data = review.review_data;
  const thisWeek = data?.this_week;
  const periodization = data?.periodization;
  const verdict = data?.verdict ?? [];
  const recommendations = data?.recommendations ?? [];

  return (
    <div className="stagger-in space-y-6">
      <div className="flex items-baseline justify-between gap-3">
        <h1 className="font-display text-2xl font-bold tracking-tight text-ink">
          週次レビュー
        </h1>
        <Link
          to="/weekly-reviews"
          className="text-sm font-medium text-slate-500 hover:text-ink"
        >
          ← 一覧へ
        </Link>
      </div>
      <p className="font-numeric text-sm tabular-nums text-slate-500">
        {review.week_start_date} 〜 {review.week_end_date}
      </p>

      {data == null ? (
        <p className="py-4 text-center text-sm text-slate-500">
          レビューデータがありません
        </p>
      ) : (
        <>
          {/* This-week actuals */}
          <Section title="実績サマリー">
            {thisWeek != null ? (
              <div className="space-y-1 text-sm text-slate-700">
                {thisWeek.volume_km != null && (
                  <p>
                    <span className="font-medium text-slate-500">走行距離: </span>
                    {thisWeek.volume_km} km
                  </p>
                )}
                {thisWeek.run_count != null && (
                  <p>
                    <span className="font-medium text-slate-500">ラン回数: </span>
                    {thisWeek.run_count} 回
                  </p>
                )}
                {thisWeek.hr_discipline != null && (
                  <p>
                    <span className="font-medium text-slate-500">心拍管理: </span>
                    {thisWeek.hr_discipline}
                  </p>
                )}
                {Array.isArray(thisWeek.highlights) &&
                  thisWeek.highlights.length > 0 && (
                    <ul className="list-disc space-y-0.5 pl-5 text-slate-600">
                      {thisWeek.highlights.map((h, i) => (
                        <li key={i}>{h}</li>
                      ))}
                    </ul>
                  )}
              </div>
            ) : (
              <p className="text-sm text-slate-500">実績データがありません</p>
            )}
          </Section>

          {/* Periodization (#286) — render only when present */}
          {periodization != null && (
            <Section title="目標逆算フェーズ">
              <div className="space-y-1 text-sm text-slate-700">
                {periodization.a_race != null && (
                  <p>
                    <span className="font-medium text-slate-500">
                      A レース: </span>
                    {periodization.a_race}
                    {periodization.weeks_to_a_race != null
                      ? `（残り ${periodization.weeks_to_a_race} 週）`
                      : "（残り週数 未確定）"}
                  </p>
                )}
                {periodization.b_race != null && (
                  <p>
                    <span className="font-medium text-slate-500">
                      B レース: </span>
                    {periodization.b_race}
                    {periodization.weeks_to_b_race != null
                      ? `（残り ${periodization.weeks_to_b_race} 週）`
                      : "（残り週数 未確定）"}
                  </p>
                )}
                {periodization.expected_phase != null && (
                  <p>
                    <span className="font-medium text-slate-500">
                      あるべきフェーズ: </span>
                    {periodization.expected_phase}
                  </p>
                )}
                {periodization.garmin_phase != null && (
                  <p>
                    <span className="font-medium text-slate-500">
                      Garmin フェーズ: </span>
                    {periodization.garmin_phase}
                  </p>
                )}
                {periodization.gap != null && (
                  <p>
                    <span className="font-medium text-slate-500">ギャップ: </span>
                    {periodization.gap}
                  </p>
                )}
              </div>
            </Section>
          )}

          {/* Verdict table — target-week plan evaluation */}
          <Section title="対象週プラン評価">
            {verdict.length > 0 ? (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs tracking-wide text-slate-500 uppercase">
                    <th className="px-2 py-2 text-left font-medium">日付</th>
                    <th className="px-2 py-2 text-left font-medium">
                      セッション
                    </th>
                    <th className="px-2 py-2 text-center font-medium">評価</th>
                    <th className="px-2 py-2 text-left font-medium">コメント</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {verdict.map((v, i) => (
                    <tr key={i} className="hover:bg-slate-50">
                      <td className="px-2 py-2 text-left font-numeric tabular-nums text-slate-700">
                        {v.date ?? "-"}
                      </td>
                      <td className="px-2 py-2 text-left text-slate-700">
                        {v.session ?? "-"}
                      </td>
                      <td className="px-2 py-2 text-center text-base">
                        {v.rating ?? "-"}
                      </td>
                      <td className="px-2 py-2 text-left text-slate-600">
                        {v.comment ?? "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="text-sm text-slate-500">評価データがありません</p>
            )}
          </Section>

          {/* Goal alignment */}
          {data.goal_alignment != null && (
            <Section title="目標との整合">
              <p className="text-sm text-slate-700">{data.goal_alignment}</p>
            </Section>
          )}

          {/* Recommendations */}
          {recommendations.length > 0 && (
            <Section title="推奨アクション">
              <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
                {recommendations.map((rec, i) => (
                  <li key={i}>{rec}</li>
                ))}
              </ul>
            </Section>
          )}

          {/* Overall */}
          {data.overall != null && (
            <Section title="総評">
              <p className="text-sm text-slate-700">{data.overall}</p>
            </Section>
          )}
        </>
      )}
    </div>
  );
}
