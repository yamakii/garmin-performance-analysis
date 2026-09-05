import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMonthPlan, useWeeklyReviewVersions } from "../api/hooks";
import { CARD_CLASS } from "../components/Card";
import ClampedProse from "../components/ClampedProse";
import Disclosure from "../components/Disclosure";
import EmptyState from "../components/EmptyState";
import { PageError, PageLoading } from "../components/PageState";
import SectionHeading from "../components/SectionHeading";
import SectionNav, { type NavItem } from "../components/SectionNav";
import StatusBadge from "../components/StatusBadge";
import VersionSelect from "../components/VersionSelect";
import {
  sessionLabel,
  statusLabel,
  statusTone,
  targetSummary,
} from "../components/plan/DayCell";
import { META_LABEL, SUBCARD } from "../components/report/ReportCard";
import { usePageTitle } from "../hooks/usePageTitle";
import { formatDate, humanizeKey, weekEndIso } from "../utils/format";
import { formatNumber } from "../utils/formatNumber";
import { ratingMeta } from "../utils/verdictRating";

/**
 * One card. Its title is an h3 because the card lives inside a `Group` whose
 * title is the h2 (#912); the standalone 総評 card belongs to no group and
 * passes `level={2}` so the outline never claims it as a child of 次アクション.
 */
function Section({
  id,
  title,
  level = 3,
  children,
}: {
  id?: string;
  title: string;
  level?: 2 | 3;
  children: React.ReactNode;
}) {
  const Heading = level === 2 ? "h2" : "h3";
  return (
    <section
      id={id}
      className={`scroll-mt-20 ${CARD_CLASS}`}
    >
      <Heading className="mb-3 font-display text-base font-semibold text-ink">
        {title}
      </Heading>
      {children}
    </section>
  );
}

/** Eyebrow style shared with the Trends/Goal page section headers. */
const SECTION_HEADING =
  "text-xs font-semibold tracking-[0.2em] text-slate-500 uppercase";

/**
 * One meaning group: an English eyebrow + Japanese heading above the member
 * Section cards (mirrors the TrendsDashboard regrouping pattern, #645). The
 * `aria-label` mirrors the Japanese title so the region (and its membership)
 * is addressable in tests and assistive tech. Until #648 lands, this is the
 * local simple heading; it can be swapped for the shared `SectionHeading`.
 *
 * The Japanese title is the page's h2 and each member card is an h3 (#912):
 * rendering both as `<p>` left the page as an h1 followed by a flat run of
 * h2 cards, so the grouping existed visually but not in the heading outline.
 * The English eyebrow restates the title, so it stays decorative.
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
        <p aria-hidden="true" className={SECTION_HEADING}>
          {eyebrow}
        </p>
        <h2 className="mt-1 font-display text-xl font-bold tracking-tight text-ink">
          {title}
        </h2>
      </div>
      {children}
    </section>
  );
}

/**
 * Clamp shared by every prose section on this page (#906): three lines carry
 * the verdict, the rest is one click away via `ClampedProse`'s toggle.
 */
const PROSE_CLAMP_LINES = 3;

type StatTile = { label: string; value: number; unit?: string };

/** A measured number becomes a tile; anything else is dropped. */
function tile(label: string, value: unknown, unit?: string): StatTile | null {
  return typeof value === "number" && Number.isFinite(value)
    ? { label, value, unit }
    : null;
}

/**
 * Number-first tile grid, matching the EfficiencyReport form-metric tiles: the
 * figure is the headline and the label is the caption, so the week's volume and
 * body numbers read at a glance instead of hiding inside `label: value` prose.
 */
function StatTiles({ tiles }: { tiles: (StatTile | null)[] }) {
  const shown = tiles.filter((t): t is StatTile => t !== null);
  if (shown.length === 0) {
    return null;
  }
  return (
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      {shown.map(({ label, value, unit }) => (
        <div key={label} className={SUBCARD}>
          <dt className={META_LABEL}>{label}</dt>
          <dd className="mt-0.5 font-numeric text-2xl leading-none font-semibold tabular-nums text-ink">
            {/* Raw payload numbers carry float noise (volume_km 42.5333…);
                one decimal is all a weekly total needs (#915). */}
            {formatNumber(value, 1)}
            {unit != null && (
              <span className="ml-0.5 text-xs font-normal text-slate-500">
                {unit}
              </span>
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * Verdict cell: the emoji stays for scanning but is decorative, and the word it
 * stands for is the text that is actually announced and read (#912). An
 * unrecognized rating is shown as-is, since its text is all we know.
 */
function VerdictBadge({ rating }: { rating: string }) {
  const { tone, label } = ratingMeta(rating);
  if (label === rating) {
    return <StatusBadge tone={tone}>{rating}</StatusBadge>;
  }
  return (
    <StatusBadge tone={tone}>
      <span aria-hidden="true">{rating}</span> {label}
    </StatusBadge>
  );
}

/** "Aレース（フルマラソン）まで 12週" countdown label, or null when unknown. */
function raceCountdown(
  label: string,
  race: string | null | undefined,
  weeks: number | null | undefined,
): string | null {
  if (race == null && weeks == null) {
    return null;
  }
  const name = race != null ? `（${race}）` : "";
  const remaining = typeof weeks === "number" ? `${weeks}週` : "残り週数 未確定";
  return `${label}レース${name}まで ${remaining}`;
}

/**
 * Page title + the way back to the list. Shared with the empty state so an
 * unknown week is still a navigable page rather than a dead end.
 */
function PageHeader() {
  return (
    <div className="flex items-start justify-between gap-3">
      <SectionHeading eyebrow="Weekly Review" title="週次レビュー" />
      <Link
        to="/weekly-reviews"
        className="text-sm font-medium text-slate-500 hover:text-ink"
      >
        ← 一覧へ
      </Link>
    </div>
  );
}

export default function WeeklyReviewDetail() {
  const { weekStart } = useParams<{ weekStart: string }>();
  usePageTitle(weekStart != null ? `週次レビュー ${weekStart}` : "週次レビュー");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const versionsQuery = useWeeklyReviewVersions(weekStart);
  const versions = versionsQuery.data ?? [];
  // The week's structured prescriptions live in the month grid's payload
  // (#983); the review page shows them with the coach's verdict merged in.
  const monthPlanQuery = useMonthPlan(weekStart?.slice(0, 7));

  if (versionsQuery.isPending) {
    return <PageLoading />;
  }
  if (versionsQuery.error) {
    return (
      <PageError
        error={versionsQuery.error}
        onRetry={() => void versionsQuery.refetch()}
      />
    );
  }
  // An unreviewed (or mistyped) week has no versions. It used to render
  // nothing at all — a white page with no explanation and no way back (#914).
  if (versions.length === 0) {
    return (
      <div className="stagger-in space-y-6">
        <PageHeader />
        <EmptyState
          message="この週のレビューはありません"
          hint={
            <Link
              to="/weekly-reviews"
              className="font-medium text-signal-ink underline underline-offset-2 hover:text-ink"
            >
              週次レビュー一覧へ
            </Link>
          }
        />
      </div>
    );
  }

  const review = versions[Math.min(selectedIndex, versions.length - 1)];
  const data = review.review_data;
  const thisWeek = data?.this_week;
  const periodization = data?.periodization;
  const verdict = data?.verdict ?? [];
  const recommendations = data?.recommendations ?? [];
  const garminNextWeek = data?.garmin_next_week ?? [];
  // Only calendar items that contradict the block are saved (#980), so the
  // Garmin card states the conflicts. Reviews written before the block ledger
  // keep their raw planned-workout table.
  const garminConflicts = data?.garmin_conflicts ?? [];
  const showConflicts = garminConflicts.length > 0;
  const planWeeks = monthPlanQuery.data?.weeks;
  const planWeek = Array.isArray(planWeeks)
    ? (planWeeks.find((week) => week.week_start === weekStart) ?? null)
    : null;
  const prescriptions = (planWeek?.days ?? []).flatMap((day) =>
    day.prescriptions.map((prescription) => ({ ...prescription, date: day.date })),
  );
  // The verdict is per day, so it merges onto the prescription of that day
  // instead of being replaced by it.
  const verdictByDate = new Map(
    verdict
      .filter((row) => row.date != null)
      .map((row) => [row.date as string, row]),
  );
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
  const expectedPhase = periodization?.expected_phase;
  const garminPhase = periodization?.garmin_phase;
  // The two phase chips already carry the comparison, so the gap sentence only
  // earns a line of its own when they disagree (or one of them is missing).
  const showPhaseGap =
    periodization?.gap != null && expectedPhase !== garminPhase;
  const raceCountdowns = [
    raceCountdown("A", periodization?.a_race, periodization?.weeks_to_a_race),
    raceCountdown("B", periodization?.b_race, periodization?.weeks_to_b_race),
  ].filter((label): label is string => label != null);
  // `this_week` is always the *previous* week's actuals — the material the
  // plan week is judged against (the key keeps its old name for
  // compatibility). Labelling it 今週の実績 read as "this week" no matter which
  // week was open (#931), so the saved `actuals_week_start` names the week it
  // really covers. Older records without that field keep the bare label.
  const actualsWeekStart = data?.actuals_week_start;
  const actualsWeekEnd = weekEndIso(actualsWeekStart);
  const actualsTitle =
    actualsWeekStart != null && actualsWeekEnd != null
      ? `実績（${formatDate(actualsWeekStart)} 〜 ${formatDate(actualsWeekEnd)}）`
      : "実績";
  const [firstRecommendation, ...moreRecommendations] = recommendations;
  const hasNextActions =
    recommendations.length > 0 ||
    garminNextWeek.length > 0 ||
    showConflicts ||
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
          showConflicts
            ? { id: "wr-garmin", label: "Garmin との衝突" }
            : garminNextWeek.length > 0
              ? { id: "wr-garmin", label: "来週のGarminワークアウト" }
              : null,
          data.continuity_note != null
            ? { id: "wr-continuity", label: "前回からの継続性" }
            : null,
          data.overall != null ? { id: "wr-overall", label: "総評" } : null,
        ].filter((item): item is NavItem => item !== null);

  return (
    <div className="stagger-in space-y-6">
      <PageHeader />
      <p className="font-numeric text-sm tabular-nums text-slate-500">
        {formatDate(review.week_start_date)} 〜 {formatDate(review.week_end_date)}
      </p>

      <VersionSelect
        id="version-select"
        options={versions.map((v) => ({
          key: String(v.review_id),
          stamp: v.created_at ?? v.review_date,
        }))}
        selectedIndex={selectedIndex}
        onSelect={setSelectedIndex}
      />

      {data == null ? (
        <p className="py-4 text-center text-sm text-slate-500">
          レビューデータがありません
        </p>
      ) : (
        <>
          {/* Sticky in-page table of contents (rendered sections only) */}
          <SectionNav items={navItems} />

          {/* ① Actuals week (W-1) — actuals, body, recovery */}
          <Group eyebrow="Actuals" title={actualsTitle}>
            {/* Actuals-week totals */}
            <Section id="wr-actuals" title="実績サマリー">
              {thisWeek != null ? (
                <div className="space-y-3 text-sm text-slate-700">
                  <StatTiles
                    tiles={[
                      tile("走行距離", thisWeek.volume_km, "km"),
                      tile("ラン回数", thisWeek.run_count, "回"),
                    ]}
                  />
                  {(thisWeek.hr_discipline != null ||
                    intensityEntries.length > 0) && (
                    <div className="flex flex-wrap items-center gap-2">
                      {thisWeek.hr_discipline != null && (
                        <StatusBadge tone="info">
                          {thisWeek.hr_discipline}
                        </StatusBadge>
                      )}
                      {intensityEntries.map(([k, v]) => (
                        <span
                          key={k}
                          className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600"
                        >
                          {humanizeKey(k)}: {String(v)}
                        </span>
                      ))}
                    </div>
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

            {/* Weight tracking (#597) */}
            {weightTracking != null && (
              <Section id="wr-weight" title="体重トラッキング">
                <div className="space-y-3 text-sm text-slate-700">
                  <StatTiles
                    tiles={[
                      tile("直近中央値", weightTracking.recent_median_kg, "kg"),
                      tile("BMI", weightTracking.bmi),
                    ]}
                  />
                  {(weightTracking.trend != null ||
                    weightTracking.week_classification != null ||
                    weightTracking.flag != null) && (
                    <div className="flex flex-wrap items-center gap-2">
                      {weightTracking.trend != null && (
                        <StatusBadge tone="info">
                          {weightTracking.trend}
                        </StatusBadge>
                      )}
                      {weightTracking.week_classification != null && (
                        <StatusBadge tone="info">
                          {weightTracking.week_classification}
                        </StatusBadge>
                      )}
                      {/* A flag is the agent raising a concern — warn tone. */}
                      {weightTracking.flag != null && (
                        <StatusBadge tone="warn">
                          {weightTracking.flag}
                        </StatusBadge>
                      )}
                    </div>
                  )}
                  {weightTracking.target_first != null && (
                    <p className="text-xs text-slate-500">
                      第一目標: {weightTracking.target_first}
                    </p>
                  )}
                </div>
              </Section>
            )}

            {/* Recovery (#597) — string only for now */}
            {typeof recovery === "string" && (
              <Section id="wr-recovery" title="リカバリー">
                <ClampedProse text={recovery} lines={PROSE_CLAMP_LINES} />
              </Section>
            )}
          </Group>

          {/* ② Assessment — plan verdict, goal alignment, periodization, ramp */}
          <Group eyebrow="Assessment" title="評価">
            {/* Prescriptions (with the verdict merged in) — target-week plan
                evaluation. Weeks that predate the structured rows keep the
                verdict-only table below. */}
            <Section id="wr-verdict" title="対象週プラン評価">
              {prescriptions.length > 0 ? (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs tracking-wide text-slate-500 uppercase">
                      <th scope="col" className="px-2 py-2 text-left font-medium">
                        日付
                      </th>
                      <th scope="col" className="px-2 py-2 text-left font-medium">
                        セッション
                      </th>
                      <th scope="col" className="px-2 py-2 text-left font-medium">
                        目標
                      </th>
                      <th
                        scope="col"
                        className="px-2 py-2 text-center font-medium"
                      >
                        状態
                      </th>
                      <th
                        scope="col"
                        className="px-2 py-2 text-center font-medium"
                      >
                        評価
                      </th>
                      <th scope="col" className="px-2 py-2 text-left font-medium">
                        コメント
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {prescriptions.map((prescription) => {
                      const graded = verdictByDate.get(prescription.date);
                      return (
                        <tr
                          key={prescription.prescription_id}
                          className="hover:bg-slate-50"
                        >
                          <td className="px-2 py-2 text-left font-numeric tabular-nums text-slate-700">
                            {prescription.date}
                          </td>
                          <td className="px-2 py-2 text-left text-slate-700">
                            {prescription.title ||
                              sessionLabel(prescription.session_type)}
                          </td>
                          <td className="px-2 py-2 text-left font-numeric tabular-nums text-slate-600">
                            {targetSummary(prescription) || "-"}
                          </td>
                          <td className="px-2 py-2 text-center">
                            <StatusBadge tone={statusTone(prescription.status)}>
                              {statusLabel(prescription.status)}
                            </StatusBadge>
                          </td>
                          <td className="px-2 py-2 text-center">
                            {graded?.rating != null ? (
                              <VerdictBadge rating={graded.rating} />
                            ) : (
                              "-"
                            )}
                          </td>
                          <td className="px-2 py-2 text-left text-slate-600">
                            {graded?.comment ?? "-"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              ) : verdict.length > 0 ? (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs tracking-wide text-slate-500 uppercase">
                      <th scope="col" className="px-2 py-2 text-left font-medium">
                        日付
                      </th>
                      <th scope="col" className="px-2 py-2 text-left font-medium">
                        セッション
                      </th>
                      <th
                        scope="col"
                        className="px-2 py-2 text-center font-medium"
                      >
                        評価
                      </th>
                      <th scope="col" className="px-2 py-2 text-left font-medium">
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
                        <td className="px-2 py-2 text-center">
                          {v.rating != null ? (
                            <VerdictBadge rating={v.rating} />
                          ) : (
                            "-"
                          )}
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
                <ClampedProse
                  text={data.goal_alignment}
                  lines={PROSE_CLAMP_LINES}
                />
              </Section>
            )}

            {/* Periodization (#286) — render only when present */}
            {periodization != null && (
              <Section id="wr-periodization" title="目標逆算フェーズ">
                <div className="space-y-3 text-sm text-slate-700">
                  {raceCountdowns.length > 0 && (
                    <div className="flex flex-wrap items-center gap-2">
                      {raceCountdowns.map((label) => (
                        <StatusBadge key={label} tone="info">
                          {label}
                        </StatusBadge>
                      ))}
                    </div>
                  )}
                  {(expectedPhase != null || garminPhase != null) && (
                    <div className="flex flex-wrap items-center gap-2">
                      {expectedPhase != null && (
                        <StatusBadge tone="info">
                          想定 {expectedPhase}
                        </StatusBadge>
                      )}
                      {garminPhase != null && (
                        <StatusBadge tone={showPhaseGap ? "warn" : "info"}>
                          Garmin {garminPhase}
                        </StatusBadge>
                      )}
                    </div>
                  )}
                  {showPhaseGap && (
                    <p className="text-xs text-slate-500">
                      ギャップ: {periodization.gap}
                    </p>
                  )}
                </div>
              </Section>
            )}

            {/* Weekly ramp (#597) — string only for now */}
            {typeof weeklyRamp === "string" && (
              <Section id="wr-ramp" title="週次ランプ">
                <ClampedProse text={weeklyRamp} lines={PROSE_CLAMP_LINES} />
              </Section>
            )}
          </Group>

          {/* ③ Next — recommendations, planned workouts, continuity */}
          {hasNextActions && (
            <Group eyebrow="Next" title="次アクション">
              {/* Recommendations */}
              {recommendations.length > 0 && (
                <Section id="wr-recommendations" title="推奨アクション">
                  {/* The lead action is the one to act on; the rest are folded
                      away so the card states a single next step (#906). */}
                  <p className="text-sm font-medium text-slate-800">
                    {firstRecommendation}
                  </p>
                  {moreRecommendations.length > 0 && (
                    <Disclosure
                      title={`他の推奨 ${moreRecommendations.length}件`}
                      className="mt-3"
                    >
                      <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
                        {moreRecommendations.map((rec, i) => (
                          <li key={i}>{rec}</li>
                        ))}
                      </ul>
                    </Disclosure>
                  )}
                </Section>
              )}

              {/* Garmin conflicts (#980): only the calendar items that
                  contradict the block are worth acting on. */}
              {showConflicts && (
                <Section id="wr-garmin" title="Garmin との衝突">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-xs tracking-wide text-slate-500 uppercase">
                        <th
                          scope="col"
                          className="px-2 py-2 text-left font-medium"
                        >
                          日付
                        </th>
                        <th
                          scope="col"
                          className="px-2 py-2 text-left font-medium"
                        >
                          Garmin の予定
                        </th>
                        <th
                          scope="col"
                          className="px-2 py-2 text-left font-medium"
                        >
                          理由
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {garminConflicts.map((conflict, i) => (
                        <tr key={i} className="hover:bg-slate-50">
                          <td className="px-2 py-2 text-left font-numeric tabular-nums text-slate-700">
                            {conflict.date ?? "-"}
                          </td>
                          <td className="px-2 py-2 text-left text-slate-700">
                            {conflict.garmin_title ?? "-"}
                          </td>
                          <td className="px-2 py-2 text-left text-slate-600">
                            {conflict.reason ?? "-"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Section>
              )}

              {/* Garmin next-week planned workouts (#597) — pre-ledger reviews */}
              {!showConflicts && garminNextWeek.length > 0 && (
                <Section id="wr-garmin" title="来週のGarminワークアウト">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-xs tracking-wide text-slate-500 uppercase">
                        <th
                          scope="col"
                          className="px-2 py-2 text-left font-medium"
                        >
                          日付
                        </th>
                        <th
                          scope="col"
                          className="px-2 py-2 text-left font-medium"
                        >
                          種別
                        </th>
                        <th
                          scope="col"
                          className="px-2 py-2 text-left font-medium"
                        >
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
                  <ClampedProse
                    text={data.continuity_note}
                    lines={PROSE_CLAMP_LINES}
                  />
                </Section>
              )}
            </Group>
          )}

          {/* Overall — closing verdict, standalone (no parent Group → h2) */}
          {data.overall != null && (
            <Section id="wr-overall" title="総評" level={2}>
              <ClampedProse text={data.overall} lines={PROSE_CLAMP_LINES} />
            </Section>
          )}
        </>
      )}
    </div>
  );
}
