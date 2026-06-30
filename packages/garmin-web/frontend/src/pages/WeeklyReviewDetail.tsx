import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { fetchWeeklyReviewVersions } from "../api/client";
import SectionHeading from "../components/SectionHeading";
import SectionNav, { type NavItem } from "../components/SectionNav";
import type { WeeklyReview } from "../types";

function Section({
  id,
  title,
  children,
}: {
  id?: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section
      id={id}
      className="scroll-mt-20 rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <h2 className="mb-3 font-display text-base font-semibold text-ink">
        {title}
      </h2>
      {children}
    </section>
  );
}

/** Eyebrow style shared with the Trends/Goal page section headers. */
const SECTION_HEADING =
  "text-xs font-semibold tracking-[0.2em] text-slate-400 uppercase";

/**
 * One meaning group: an English eyebrow + Japanese heading above the member
 * Section cards (mirrors the TrendsDashboard regrouping pattern, #645). The
 * `aria-label` mirrors the Japanese title so the region (and its membership)
 * is addressable in tests and assistive tech. Until #648 lands, this is the
 * local simple heading; it can be swapped for the shared `SectionHeading`.
 */
function Group({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section aria-label={title} className="space-y-4">
      <div>
        <p className={SECTION_HEADING}>{eyebrow}</p>
        <p className="mt-1 font-display text-xl font-bold tracking-tight text-ink">
          {title}
        </p>
      </div>
      {children}
    </section>
  );
}

function versionLabel(version: WeeklyReview, isLatest: boolean): string {
  const stamp = version.created_at ?? version.review_date ?? "日時不明";
  return isLatest ? `${stamp}（最新）` : stamp;
}

export default function WeeklyReviewDetail() {
  const { weekStart } = useParams<{ weekStart: string }>();
  const [versions, setVersions] = useState<WeeklyReview[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (weekStart == null) {
      return;
    }
    let cancelled = false;
    setLoading(true);
    fetchWeeklyReviewVersions(weekStart)
      .then((data) => {
        if (!cancelled) {
          setVersions(data);
          setSelectedIndex(0);
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
  if (versions.length === 0) {
    return null;
  }

  const review = versions[Math.min(selectedIndex, versions.length - 1)];
  const data = review.review_data;
  const thisWeek = data?.this_week;
  const periodization = data?.periodization;
  const verdict = data?.verdict ?? [];
  const recommendations = data?.recommendations ?? [];
  const garminNextWeek = data?.garmin_next_week ?? [];
  const intensityDistribution = thisWeek?.intensity_distribution;
  const intensityEntries =
    intensityDistribution != null
      ? Object.entries(intensityDistribution).filter(
          ([, v]) => typeof v === "number" || typeof v === "string",
        )
      : [];
  const weightTracking = data?.weight_tracking;
  const recovery = data?.recovery;
  const weeklyRamp = data?.weekly_ramp;
  const hasNextActions =
    recommendations.length > 0 ||
    garminNextWeek.length > 0 ||
    data?.continuity_note != null;

  // In-page nav: list only the Section cards that actually render below.
  const navItems: NavItem[] =
    data == null
      ? []
      : [
          { id: "wr-actuals", label: "実績サマリー" },
          weightTracking != null
            ? { id: "wr-weight", label: "体重トラッキング" }
            : null,
          typeof recovery === "string"
            ? { id: "wr-recovery", label: "リカバリー" }
            : null,
          { id: "wr-verdict", label: "対象週プラン評価" },
          data.goal_alignment != null
            ? { id: "wr-goal", label: "目標との整合" }
            : null,
          periodization != null
            ? { id: "wr-periodization", label: "目標逆算フェーズ" }
            : null,
          typeof weeklyRamp === "string"
            ? { id: "wr-ramp", label: "週次ランプ" }
            : null,
          recommendations.length > 0
            ? { id: "wr-recommendations", label: "推奨アクション" }
            : null,
          garminNextWeek.length > 0
            ? { id: "wr-garmin", label: "来週のGarminワークアウト" }
            : null,
          data.continuity_note != null
            ? { id: "wr-continuity", label: "前回からの継続性" }
            : null,
          data.overall != null ? { id: "wr-overall", label: "総評" } : null,
        ].filter((item): item is NavItem => item !== null);

  return (
    <div className="stagger-in space-y-6">
      <div className="flex items-start justify-between gap-3">
        <SectionHeading eyebrow="Weekly Review" title="週次レビュー" />
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

      {versions.length > 1 && (
        <div className="flex flex-wrap items-center gap-3">
          <label
            htmlFor="version-select"
            className="text-sm font-medium text-slate-500"
          >
            版を選択:
          </label>
          <select
            id="version-select"
            value={selectedIndex}
            onChange={(e) => setSelectedIndex(Number(e.target.value))}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-ink shadow-sm focus:border-ink focus:outline-none"
          >
            {versions.map((v, i) => (
              <option key={v.review_id} value={i}>
                {versionLabel(v, i === 0)}
              </option>
            ))}
          </select>
          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">
            全{versions.length}版
          </span>
        </div>
      )}

      {data == null ? (
        <p className="py-4 text-center text-sm text-slate-500">
          レビューデータがありません
        </p>
      ) : (
        <>
          {/* Sticky in-page table of contents (rendered sections only) */}
          <SectionNav items={navItems} />

          {/* ① This week — actuals, body, recovery */}
          <Group eyebrow="This Week" title="今週の実績">
            {/* This-week actuals */}
            <Section id="wr-actuals" title="実績サマリー">
              {thisWeek != null ? (
                <div className="space-y-1 text-sm text-slate-700">
                  {thisWeek.volume_km != null && (
                    <p>
                      <span className="font-medium text-slate-500">
                        走行距離: </span>
                      {thisWeek.volume_km} km
                    </p>
                  )}
                  {thisWeek.run_count != null && (
                    <p>
                      <span className="font-medium text-slate-500">
                        ラン回数: </span>
                      {thisWeek.run_count} 回
                    </p>
                  )}
                  {thisWeek.hr_discipline != null && (
                    <p>
                      <span className="font-medium text-slate-500">
                        心拍管理: </span>
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
                  {intensityEntries.length > 0 && (
                    <div className="flex flex-wrap gap-2 pt-1">
                      {intensityEntries.map(([k, v]) => (
                        <span
                          key={k}
                          className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600"
                        >
                          {k}: {String(v)}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-sm text-slate-500">実績データがありません</p>
              )}
            </Section>

            {/* Weight tracking (#597) */}
            {weightTracking != null && (
              <Section id="wr-weight" title="体重トラッキング">
                <div className="space-y-1 text-sm text-slate-700">
                  {weightTracking.recent_median_kg != null && (
                    <p>
                      <span className="font-medium text-slate-500">
                        直近中央値: </span>
                      {weightTracking.recent_median_kg} kg
                    </p>
                  )}
                  {weightTracking.bmi != null && (
                    <p>
                      <span className="font-medium text-slate-500">BMI: </span>
                      {weightTracking.bmi}
                    </p>
                  )}
                  {weightTracking.trend != null && (
                    <p>
                      <span className="font-medium text-slate-500">傾向: </span>
                      {weightTracking.trend}
                    </p>
                  )}
                  {weightTracking.week_classification != null && (
                    <p>
                      <span className="font-medium text-slate-500">
                        週分類: </span>
                      {weightTracking.week_classification}
                    </p>
                  )}
                  {weightTracking.flag != null && (
                    <p>
                      <span className="font-medium text-slate-500">注意: </span>
                      {weightTracking.flag}
                    </p>
                  )}
                  {weightTracking.target_first != null && (
                    <p>
                      <span className="font-medium text-slate-500">
                        第一目標: </span>
                      {weightTracking.target_first}
                    </p>
                  )}
                </div>
              </Section>
            )}

            {/* Recovery (#597) — string only for now */}
            {typeof recovery === "string" && (
              <Section id="wr-recovery" title="リカバリー">
                <p className="text-sm text-slate-700">{recovery}</p>
              </Section>
            )}
          </Group>

          {/* ② Assessment — plan verdict, goal alignment, periodization, ramp */}
          <Group eyebrow="Assessment" title="評価">
            {/* Verdict table — target-week plan evaluation */}
            <Section id="wr-verdict" title="対象週プラン評価">
              {verdict.length > 0 ? (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs tracking-wide text-slate-500 uppercase">
                      <th className="px-2 py-2 text-left font-medium">日付</th>
                      <th className="px-2 py-2 text-left font-medium">
                        セッション
                      </th>
                      <th className="px-2 py-2 text-center font-medium">評価</th>
                      <th className="px-2 py-2 text-left font-medium">
                        コメント
                      </th>
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
              <Section id="wr-goal" title="目標との整合">
                <p className="text-sm text-slate-700">{data.goal_alignment}</p>
              </Section>
            )}

            {/* Periodization (#286) — render only when present */}
            {periodization != null && (
              <Section id="wr-periodization" title="目標逆算フェーズ">
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
                      <span className="font-medium text-slate-500">
                        ギャップ: </span>
                      {periodization.gap}
                    </p>
                  )}
                </div>
              </Section>
            )}

            {/* Weekly ramp (#597) — string only for now */}
            {typeof weeklyRamp === "string" && (
              <Section id="wr-ramp" title="週次ランプ">
                <p className="text-sm text-slate-700">{weeklyRamp}</p>
              </Section>
            )}
          </Group>

          {/* ③ Next — recommendations, planned workouts, continuity */}
          {hasNextActions && (
            <Group eyebrow="Next" title="次アクション">
              {/* Recommendations */}
              {recommendations.length > 0 && (
                <Section id="wr-recommendations" title="推奨アクション">
                  <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
                    {recommendations.map((rec, i) => (
                      <li key={i}>{rec}</li>
                    ))}
                  </ul>
                </Section>
              )}

              {/* Garmin next-week planned workouts (#597) */}
              {garminNextWeek.length > 0 && (
                <Section id="wr-garmin" title="来週のGarminワークアウト">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-xs tracking-wide text-slate-500 uppercase">
                        <th className="px-2 py-2 text-left font-medium">
                          日付
                        </th>
                        <th className="px-2 py-2 text-left font-medium">
                          種別
                        </th>
                        <th className="px-2 py-2 text-left font-medium">
                          タイトル
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {garminNextWeek.map((w, i) => (
                        <tr key={i} className="hover:bg-slate-50">
                          <td className="px-2 py-2 text-left font-numeric tabular-nums text-slate-700">
                            {w.date ?? "-"}
                          </td>
                          <td className="px-2 py-2 text-left text-slate-700">
                            {w.type ?? "-"}
                          </td>
                          <td className="px-2 py-2 text-left text-slate-600">
                            {w.title ?? "-"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Section>
              )}

              {/* Continuity with the previous review (#597) */}
              {data.continuity_note != null && (
                <Section id="wr-continuity" title="前回からの継続性">
                  <p className="text-sm text-slate-700">
                    {data.continuity_note}
                  </p>
                </Section>
              )}
            </Group>
          )}

          {/* Overall — closing verdict, standalone */}
          {data.overall != null && (
            <Section id="wr-overall" title="総評">
              <p className="text-sm text-slate-700">{data.overall}</p>
            </Section>
          )}
        </>
      )}
    </div>
  );
}
