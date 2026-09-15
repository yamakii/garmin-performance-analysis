import type { JSX } from "react";
import { useGoal, useRaceReadiness } from "../api/hooks";
import Disclosure from "../components/Disclosure";
import EmptyState, { CliCommand } from "../components/EmptyState";
import { PageError, PageLoading } from "../components/PageState";
import SectionBlock from "../components/SectionBlock";
import SectionHeading from "../components/SectionHeading";
import VerdictLine from "../components/VerdictLine";
import { usePageTitle } from "../hooks/usePageTitle";
import type {
  GoalRace,
  RaceReadiness,
  RaceReadinessProgress,
  SeasonRetrospective,
} from "../types";
import { type FocusSection, parseFocusNotes } from "../utils/focusNotes";
import { formatDate, formatDateLabel, formatDistanceKm } from "../utils/format";
import {
  daysUntil,
  formatGap,
  formatTargetTime,
  pickFeaturedRace,
} from "../utils/race";
import { goalVerdict } from "../utils/verdict";

const GOAL_TYPE_LABELS: Record<string, string> = {
  marathon: "フルマラソン",
  full: "フルマラソン",
  half: "ハーフマラソン",
  "10k": "10km",
  "5k": "5km",
  ultra: "ウルトラ",
};

function goalTypeLabel(goalType: string | null): string {
  if (goalType == null) {
    return "-";
  }
  return GOAL_TYPE_LABELS[goalType.toLowerCase()] ?? goalType;
}

const STATUS_LABELS: Record<string, string> = {
  active: "進行中",
  planned: "予定",
  done: "完了",
  completed: "完了",
  cancelled: "中止",
};

function statusLabel(status: string | null): string {
  if (status == null) {
    return "-";
  }
  return STATUS_LABELS[status.toLowerCase()] ?? status;
}

function isPriorityA(race: GoalRace): boolean {
  return (race.priority ?? "").toUpperCase() === "A";
}

function isPriorityB(race: GoalRace): boolean {
  return (race.priority ?? "").toUpperCase() === "B";
}

/** "2099-02-01 SUN" — the header-style date the brief uses for a race day. */
function raceDateLabel(iso: string | null): string {
  if (iso == null) {
    return "日程未定";
  }
  const weekday = formatDateLabel(iso).split(" ")[1];
  const day = formatDate(iso);
  return weekday == null || weekday === "" ? day : `${day} ${weekday}`;
}

/**
 * Which featured race the readiness prediction belongs to. The API computes
 * readiness against a single goal race, so the prediction is attached to the
 * column whose name matches; when the payload carries no usable name we fall
 * back to the primary (A) race so the prediction is never orphaned.
 */
function findPredictionRace(
  races: GoalRace[],
  readiness: RaceReadiness | null,
): GoalRace | null {
  if (readiness?.progress == null) {
    return null;
  }
  const name = readiness.goal?.race_name ?? null;
  if (name != null) {
    const byName = races.find((race) => race.race_name === name);
    if (byName != null) {
      return byName;
    }
  }
  return races.find(isPriorityA) ?? races[0] ?? null;
}

/**
 * "現在 VDOT 49.2 · 予測 フル 3:26:00 · ハーフ 1:38:30" — the fitness the
 * verdict's prediction rests on, or why there is none.
 */
function fitnessLead(readiness: RaceReadiness | null): string | null {
  if (readiness == null) {
    return null;
  }
  const vdot = readiness.current_vdot;
  if (vdot == null) {
    return "直近のランニングデータが不足しているため、予測タイムは算出できませんでした。";
  }
  const parts = [`現在 VDOT ${vdot.toFixed(1)}`];
  const full = readiness.predicted_times.full;
  const half = readiness.predicted_times.half;
  if (full != null) {
    parts.push(`予測 フル ${formatTargetTime(full)}`);
  }
  if (half != null) {
    parts.push(`ハーフ ${formatTargetTime(half)}`);
  }
  return `${parts.join(" · ")}。`;
}

/**
 * The A / B band: two columns, one countdown each, with the VDOT prediction
 * folded into the column it was computed against.
 *
 * The A tag is filled and the B tag outlined, which is the whole hierarchy the
 * band needs — the numeral already carries the urgency, so the second race
 * does not have to be shouted in a different colour (#1122).
 */
function RaceColumns({
  races,
  predictionRaceId,
  progress,
  vdot,
}: {
  races: GoalRace[];
  predictionRaceId: number | null;
  progress: RaceReadinessProgress | null;
  vdot: number | null;
}): JSX.Element {
  return (
    <section
      aria-label="目標レース"
      className="grid border-t border-b border-t-ink border-b-hairline md:grid-cols-2"
    >
      {races.map((race, index) => (
        <RaceColumn
          key={race.goal_id}
          race={race}
          first={index === 0}
          progress={race.goal_id === predictionRaceId ? progress : null}
          vdot={vdot}
        />
      ))}
    </section>
  );
}

function RaceColumn({
  race,
  first,
  progress,
  vdot,
}: {
  race: GoalRace;
  first: boolean;
  progress: RaceReadinessProgress | null;
  vdot: number | null;
}): JSX.Element {
  const days = daysUntil(race.race_date);
  const priority = (race.priority ?? "?").toUpperCase();
  const tagClass =
    priority === "A"
      ? "rounded-sm bg-ink px-1.5 py-[3px] font-medium text-paper"
      : "rounded-sm border border-ink px-1.5 py-[3px] font-medium text-ink";

  return (
    <div
      className={`flex flex-col gap-3 py-5 ${
        first ? "md:border-r md:border-hairline md:pr-8" : "md:pl-8"
      }`}
    >
      <p className="flex flex-wrap items-center gap-2 font-mono text-xs text-ink-muted">
        <span className={tagClass}>{priority}</span>
        <span>
          {race.race_name ?? "レース未設定"} · {raceDateLabel(race.race_date)} ·{" "}
          {goalTypeLabel(race.goal_type)} {formatDistanceKm(race.distance_km, 1)}
        </span>
      </p>

      {days == null ? (
        <p className="text-sm text-ink-muted">日程未定</p>
      ) : days < 0 ? (
        <p className="text-sm text-ink-muted">開催済み</p>
      ) : (
        <p className="font-mono text-[64px] leading-none font-medium text-ink">
          {days}
          <span className="ml-1 font-sans text-lg font-bold">日</span>
        </p>
      )}

      <dl className="grid grid-cols-3 gap-x-4 gap-y-1">
        <div>
          <dt className="font-mono text-xs text-ink-muted">目標</dt>
          <dd className="mt-0.5 font-mono text-[15px] text-ink">
            {formatTargetTime(race.target_time_seconds)}
          </dd>
        </div>
        {progress != null && (
          <>
            <div>
              <dt className="font-mono text-xs text-ink-muted">
                予測{vdot != null ? ` (VDOT ${vdot.toFixed(1)})` : ""}
              </dt>
              <dd className="mt-0.5 font-mono text-[15px] text-ink">
                {formatTargetTime(progress.predicted_time_seconds)}
              </dd>
            </div>
            <div>
              <dt className="font-mono text-xs text-ink-muted">差</dt>
              {/*
               * A positive gap means the prediction is slower than the target,
               * which is the only direction the reader has to act on.
               */}
              <dd
                className={`mt-0.5 font-mono text-[15px] ${
                  progress.gap_seconds > 0
                    ? "font-bold text-status-warn"
                    : "text-ink"
                }`}
              >
                {formatGap(progress.gap_seconds)}
              </dd>
            </div>
          </>
        )}
      </dl>

      {race.notes != null && race.notes.trim() !== "" && (
        <p className="text-[13px] leading-[1.6] text-ink-muted">{race.notes}</p>
      )}
    </div>
  );
}

/** One `【見出し】本文` section of `focus_notes`, as a ruled row. */
function FocusRow({ section }: { section: FocusSection }): JSX.Element {
  return (
    <div className="grid gap-x-8 gap-y-1 border-b border-hairline py-3 md:grid-cols-[160px_1fr]">
      <p className="text-[13px] font-bold text-ink">{section.title}</p>
      <p className="text-sm leading-[1.7] whitespace-pre-line text-ink-soft">
        {section.body}
      </p>
    </div>
  );
}

/**
 * The current phase: the one-line focus, then its rules as ruled rows.
 *
 * Only the first three rules stay open. The rest are a footnote behind a
 * disclosure — a phase is defined by its headline constraint, and a wall of
 * rules buries it (#1122).
 */
function FocusRows({ sections }: { sections: FocusSection[] }): JSX.Element {
  // An untitled section is the preamble before the first 【…】 (or the whole
  // note when it carries no headings): prose, not a rule, so it leads.
  const preamble = sections.filter((section) => section.title == null);
  const rules = sections.filter((section) => section.title != null);
  const shown = rules.slice(0, 3);
  const folded = rules.slice(3);

  return (
    <div className="flex flex-col gap-3">
      {preamble.map((section, index) => (
        <p
          // Sections are positional and have no stable id.
          // eslint-disable-next-line react/no-array-index-key
          key={index}
          className="text-[15px] leading-[1.7] whitespace-pre-line text-ink-soft"
        >
          {section.body}
        </p>
      ))}
      {rules.length > 0 && (
        <div className="border-t border-hairline">
          {shown.map((section, index) => (
            // eslint-disable-next-line react/no-array-index-key
            <FocusRow key={index} section={section} />
          ))}
          {folded.length > 0 && (
            <Disclosure title={`ルール(${folded.length}件) 展開`}>
              <div className="border-t border-hairline">
                {folded.map((section, index) => (
                  // eslint-disable-next-line react/no-array-index-key
                  <FocusRow key={index} section={section} />
                ))}
              </div>
            </Disclosure>
          )}
        </div>
      )}
    </div>
  );
}

/** One registered race that the A / B band does not headline. */
function OtherRaceRow({ race }: { race: GoalRace }): JSX.Element {
  return (
    <div className="grid items-baseline gap-x-4 gap-y-0.5 border-b border-hairline py-2.5 md:grid-cols-[120px_1fr_100px_90px_70px]">
      <span className="font-mono text-[13px] text-ink-muted">
        {race.race_date ?? "日程未定"}
      </span>
      <span className="text-sm font-bold text-ink">
        {race.race_name ?? "-"}
      </span>
      <span className="text-[13px] text-ink-soft">
        {goalTypeLabel(race.goal_type)}
      </span>
      <span className="font-mono text-[13px] text-ink-soft">
        {formatTargetTime(race.target_time_seconds)}
      </span>
      <span className="font-mono text-[11px] text-ink-muted">
        {`${race.priority ?? "-"} · ${statusLabel(race.status)}`}
      </span>
    </div>
  );
}

/** The `key_learnings` of a season, as the quoted line it is. */
function Learning({ text }: { text: string }): JSX.Element {
  return (
    <p className="border-l-2 border-ink pl-3 text-sm leading-[1.7] whitespace-pre-line text-ink-soft">
      <span className="font-bold text-ink">学び:</span> {text}
    </p>
  );
}

/**
 * One past season. The latest season's learning is the one still worth acting
 * on, so it is shown; older ones fold away behind their own trigger.
 */
function RetrospectiveRow({
  retro,
  showLearning,
}: {
  retro: SeasonRetrospective;
  showLearning: boolean;
}): JSX.Element {
  const learning = retro.key_learnings;
  const hasLearning = learning != null && learning.trim() !== "";

  return (
    <div className="grid gap-x-8 gap-y-2 border-b border-hairline py-4 md:grid-cols-[120px_1fr]">
      <div>
        <p className="text-sm font-bold text-ink">
          {retro.season_label ?? "シーズン"}
        </p>
        {(retro.period_start != null || retro.period_end != null) && (
          <p className="mt-0.5 font-mono text-xs text-ink-muted">
            {retro.period_start ?? "?"} – {retro.period_end ?? "?"}
          </p>
        )}
      </div>
      <div className="flex flex-col gap-2">
        {retro.narrative != null && (
          <p className="text-sm leading-[1.7] whitespace-pre-line text-ink-soft">
            {retro.narrative}
          </p>
        )}
        {hasLearning &&
          (showLearning ? (
            <Learning text={learning} />
          ) : (
            <Disclosure title="学びを表示">
              <Learning text={learning} />
            </Disclosure>
          ))}
      </div>
    </div>
  );
}

export default function Goal() {
  usePageTitle("目標");
  const goalQuery = useGoal();
  // Race readiness is supplementary: a failure here must not block the page,
  // so its error is ignored and the brief simply omits the prediction.
  const readinessQuery = useRaceReadiness();

  const goal = goalQuery.data ?? null;
  const readiness = readinessQuery.data ?? null;
  const loading = goalQuery.isPending;
  const error = goalQuery.error;

  if (loading) {
    return <PageLoading />;
  }
  if (error) {
    return <PageError error={error} onRetry={() => void goalQuery.refetch()} />;
  }
  // Resolved with nothing to show: the page has no header of its own to fall
  // back on, so returning null left a white screen (#914).
  if (goal == null) {
    return (
      <div className="flex flex-col gap-6">
        <SectionHeading title="目標" />
        <EmptyState
          message="目標データがありません"
          hint={
            <>
              CLI <CliCommand>/set-goal</CliCommand> で登録できます
            </>
          }
        />
      </div>
    );
  }

  const { profile, goals, retrospectives } = goal;
  const hasProfile =
    profile.current_focus != null || profile.focus_notes != null;
  const focusSections = parseFocusNotes(profile.focus_notes);
  // The A / B band headlines the first priority-A and first priority-B race
  // (with the VDOT prediction folded in); the list below carries every other
  // race, so no race appears twice on the page.
  const featuredRaces = [
    goals.find(isPriorityA),
    goals.find(isPriorityB),
  ].filter((race): race is GoalRace => race != null);
  const featuredIds = new Set(featuredRaces.map((race) => race.goal_id));
  const otherRaces = goals.filter((race) => !featuredIds.has(race.goal_id));
  const predictionRace = findPredictionRace(featuredRaces, readiness);
  // The verdict counts down to the A race when there is one; a season with
  // only lower-priority races still gets a countdown rather than "未登録".
  const verdict = goalVerdict(
    readiness,
    featuredRaces[0] ?? pickFeaturedRace(goals),
  );
  const lead = fitnessLead(readiness);

  return (
    <div className="flex flex-col gap-12">
      {/* 1. The one line: target vs prediction, and how long there is left */}
      <VerdictLine
        verdict={verdict.verdict}
        verdictTone={verdict.tone}
        rest={verdict.rest}
        lead={lead}
      />

      {/* 2. A / B countdowns, prediction folded into the race it belongs to */}
      {featuredRaces.length > 0 && (
        <RaceColumns
          races={featuredRaces}
          predictionRaceId={predictionRace?.goal_id ?? null}
          progress={readiness?.progress ?? null}
          vdot={readiness?.current_vdot ?? null}
        />
      )}

      {/* 3. What this phase asks for */}
      <SectionBlock
        title="現フェーズ"
        note={profile.updated_at != null ? `更新 ${profile.updated_at}` : undefined}
        noteMono
      >
        {hasProfile ? (
          <div className="flex flex-col gap-4">
            {profile.current_focus != null && (
              <p className="text-xl leading-snug font-bold text-ink">
                {profile.current_focus}
              </p>
            )}
            {focusSections.length > 0 && (
              <FocusRows sections={focusSections} />
            )}
          </div>
        ) : (
          <EmptyState
            message="現フェーズが登録されていません"
            hint={
              <>
                CLI <CliCommand>/set-goal</CliCommand> で登録できます
              </>
            }
          />
        )}
      </SectionBlock>

      {/* 4. Every race the band does not headline */}
      <SectionBlock title="その他のレース">
        {otherRaces.length > 0 ? (
          <div className="border-t border-hairline">
            {otherRaces.map((race) => (
              <OtherRaceRow key={race.goal_id} race={race} />
            ))}
          </div>
        ) : (
          <EmptyState
            message={
              featuredRaces.length > 0
                ? "A / B 以外のレースは登録されていません"
                : "目標レースが登録されていません"
            }
            hint={
              <>
                CLI <CliCommand>/set-goal</CliCommand> で登録できます
              </>
            }
          />
        )}
      </SectionBlock>

      {/* 5. What last season taught */}
      <SectionBlock title="昨季の振り返り">
        {retrospectives.length > 0 ? (
          <div className="border-t border-hairline">
            {retrospectives.map((retro, index) => (
              <RetrospectiveRow
                key={retro.retro_id}
                retro={retro}
                showLearning={index === 0}
              />
            ))}
          </div>
        ) : (
          <EmptyState
            message="振り返りが登録されていません"
            hint={
              <>
                CLI <CliCommand>/set-goal</CliCommand> で登録できます
              </>
            }
          />
        )}
      </SectionBlock>
    </div>
  );
}
