import EmptyState, { CliCommand } from "../components/EmptyState";
import SectionHeading from "../components/SectionHeading";
import StatusBadge, { type StatusTone } from "../components/StatusBadge";
import { useGoal, useRaceReadiness } from "../api/hooks";
import type {
  GoalRace,
  RaceReadiness,
  SeasonRetrospective,
} from "../types";
import { parseFocusNotes } from "../utils/focusNotes";

/** Format a target time in seconds as H:MM:SS (e.g. 16200 -> "4:30:00"). */
export function formatTargetTime(seconds: number | null): string {
  if (seconds == null || seconds < 0) {
    return "-";
  }
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  return `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(
    2,
    "0",
  )}`;
}

function formatDistanceKm(km: number | null): string {
  if (km == null) {
    return "-";
  }
  return `${km.toFixed(2)} km`;
}

/**
 * Whole days from today (local) until `isoDate` (YYYY-MM-DD). Returns null when
 * the date is missing or unparseable. Negative values mean the date has passed.
 * Pure so the countdown is testable without mocking the clock at call sites.
 */
export function daysUntil(
  isoDate: string | null,
  today: Date = new Date(),
): number | null {
  if (isoDate == null) {
    return null;
  }
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate.trim());
  if (match == null) {
    return null;
  }
  const target = Date.UTC(
    Number(match[1]),
    Number(match[2]) - 1,
    Number(match[3]),
  );
  const now = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.round((target - now) / 86_400_000);
}

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

/**
 * Faint topographic-contour texture (inline SVG data URI) for the hero
 * background, matching the activity report HeroHeader. Stroked in ink, used at
 * very low opacity so it reads as paper texture.
 */
const CONTOUR_PATTERN = `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='280' height='280' viewBox='0 0 280 280' fill='none' stroke='%2316213a' stroke-width='1'%3E%3Cpath d='M0 40c46-22 94 16 140-6s94-26 140-2'/%3E%3Cpath d='M0 90c46-24 94 18 140-8s94-28 140-2'/%3E%3Cpath d='M0 140c46-20 94 14 140-6s94-24 140-2'/%3E%3Cpath d='M0 190c46-26 94 20 140-8s94-30 140-2'/%3E%3Cpath d='M0 240c46-22 94 16 140-6s94-26 140-2'/%3E%3Cellipse cx='70' cy='66' rx='34' ry='13'/%3E%3Cellipse cx='70' cy='66' rx='20' ry='7'/%3E%3Cellipse cx='204' cy='214' rx='38' ry='15'/%3E%3Cellipse cx='204' cy='214' rx='22' ry='8'/%3E%3C/svg%3E")`;

/** Single big "あと N日" countdown tile inside the hero. */
function CountdownTile({
  race,
  tone,
}: {
  race: GoalRace;
  tone: "primary" | "secondary";
}) {
  const days = daysUntil(race.race_date);
  const accent = tone === "primary" ? "text-signal" : "text-gold";
  const tagBg =
    tone === "primary" ? "bg-signal/15 text-signal" : "bg-gold/15 text-amber-700";

  return (
    <div className="relative">
      <div className="flex items-center gap-2">
        <span
          className={`rounded-md px-2 py-0.5 font-numeric text-sm font-bold tracking-wide ${tagBg}`}
        >
          {race.priority ?? "?"}
        </span>
        <span className="font-display text-base font-semibold text-ink">
          {race.race_name ?? "レース未設定"}
        </span>
      </div>

      <div className="mt-3 flex items-end gap-2">
        {days == null ? (
          <span className="rounded-md bg-slate-100 px-3 py-1.5 font-display text-sm font-medium text-slate-500">
            日程未定
          </span>
        ) : days >= 0 ? (
          <>
            <span className="font-display text-xs font-medium tracking-wide text-slate-400">
              あと
            </span>
            <span
              className={`font-numeric text-6xl leading-[0.85] font-bold tabular-nums md:text-7xl ${accent}`}
            >
              {days}
            </span>
            <span className="pb-1 font-display text-lg font-semibold text-ink">
              日
            </span>
          </>
        ) : (
          <span className="rounded-md bg-slate-100 px-3 py-1.5 font-display text-sm font-medium text-slate-500">
            開催済み
          </span>
        )}
      </div>

      <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-sm">
        {race.race_date != null && (
          <div>
            <dt className="sr-only">開催日</dt>
            <dd className="font-numeric tabular-nums text-slate-500">
              {race.race_date}
            </dd>
          </div>
        )}
        <div>
          <dt className="sr-only">目標タイム</dt>
          <dd>
            <span className="text-xs text-slate-400">目標 </span>
            <span className="font-numeric text-lg font-semibold tabular-nums text-ink">
              {formatTargetTime(race.target_time_seconds)}
            </span>
          </dd>
        </div>
      </dl>
    </div>
  );
}

/** Hero band with countdowns to the A (primary) and B (secondary) races. */
function CountdownHero({ goals }: { goals: GoalRace[] }) {
  const primary = goals.find(isPriorityA) ?? null;
  const secondary = goals.find(isPriorityB) ?? null;
  const featured = [primary, secondary].filter(
    (race): race is GoalRace => race != null,
  );

  if (featured.length === 0) {
    return null;
  }

  return (
    <header className="relative overflow-hidden rounded-2xl border border-slate-200 bg-gradient-to-br from-white via-slate-50 to-slate-100 shadow-sm">
      <div
        aria-hidden="true"
        className="absolute inset-0 opacity-[0.04]"
        style={{ backgroundImage: CONTOUR_PATTERN }}
      />
      <div className="relative px-6 py-7 md:px-8">
        <SectionHeading eyebrow="Countdown" title="目標レースまで" />
        <div className="mt-6 grid gap-8 md:grid-cols-2 md:gap-12">
          {featured.map((race) => (
            <CountdownTile
              key={race.goal_id}
              race={race}
              tone={isPriorityA(race) ? "primary" : "secondary"}
            />
          ))}
        </div>
      </div>
    </header>
  );
}

/**
 * Card for one target race. Priority A is visually featured, except when the
 * same race is already headlined in the CountdownHero: passing
 * `deemphasizeFeatured` drops the signal ring / left bar so the race is not
 * featured twice on the page.
 */
function RaceCard({
  race,
  deemphasizeFeatured,
}: {
  race: GoalRace;
  deemphasizeFeatured?: boolean;
}) {
  const featured = isPriorityA(race) && deemphasizeFeatured !== true;
  const border = featured
    ? "border-signal/40 ring-1 ring-signal/20"
    : "border-slate-200";

  return (
    <article
      className={`relative overflow-hidden rounded-xl border bg-white p-5 shadow-sm ${border}`}
    >
      {featured && (
        <span
          aria-hidden="true"
          className="absolute inset-y-0 left-0 w-1 bg-signal"
        />
      )}
      <div className="flex items-start justify-between gap-3">
        <div>
          <span
            className={`inline-block rounded-md px-2 py-0.5 font-numeric text-sm font-bold tracking-wide ${
              featured ? "bg-signal/15 text-signal" : "bg-ink/5 text-ink"
            }`}
          >
            {race.priority ?? "-"}
          </span>
          <h3 className="mt-2 font-display text-lg font-semibold text-ink">
            {race.race_name ?? "-"}
          </h3>
          <p className="mt-0.5 font-numeric text-sm tabular-nums text-slate-500">
            {race.race_date ?? "日程未定"}
          </p>
        </div>
        <span className="shrink-0 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">
          {statusLabel(race.status)}
        </span>
      </div>

      <dl className="mt-4 grid grid-cols-3 gap-3 border-t border-slate-100 pt-4">
        <div>
          <dt className="text-xs tracking-wide text-slate-400">種別</dt>
          <dd className="mt-0.5 text-sm font-medium text-slate-700">
            {goalTypeLabel(race.goal_type)}
          </dd>
        </div>
        <div>
          <dt className="text-xs tracking-wide text-slate-400">距離</dt>
          <dd className="mt-0.5 font-numeric text-sm tabular-nums text-slate-700">
            {formatDistanceKm(race.distance_km)}
          </dd>
        </div>
        <div>
          <dt className="text-xs tracking-wide text-slate-400">目標タイム</dt>
          <dd className="mt-0.5 font-numeric text-base font-semibold tabular-nums text-ink">
            {formatTargetTime(race.target_time_seconds)}
          </dd>
        </div>
      </dl>

      {race.notes != null && race.notes.trim() !== "" && (
        <p className="mt-4 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600">
          {race.notes}
        </p>
      )}
    </article>
  );
}

/**
 * One focus section. Untitled sections (preamble) render as a plain lead
 * paragraph; titled sections render as a collapsible <details> card. The first
 * few titled sections are open by default; later ones stay collapsed.
 */
function FocusSectionCard({
  title,
  body,
  defaultOpen,
}: {
  title: string | null;
  body: string;
  defaultOpen: boolean;
}) {
  if (title == null) {
    return (
      <p className="text-[15px] leading-relaxed font-medium text-slate-800">
        {body}
      </p>
    );
  }

  return (
    <details
      open={defaultOpen}
      className="group rounded-lg border border-slate-200 bg-white open:border-ink/20 open:shadow-sm"
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
        <span className="flex items-center gap-2 font-display text-sm font-semibold text-ink">
          <span
            aria-hidden="true"
            className="h-3 w-3 shrink-0 rounded-full bg-signal/70"
          />
          {title}
        </span>
        <span
          aria-hidden="true"
          className="text-slate-400 transition-transform group-open:rotate-90"
        >
          ›
        </span>
      </summary>
      <p className="px-4 pb-4 text-sm leading-relaxed whitespace-pre-line text-slate-600">
        {body}
      </p>
    </details>
  );
}

/** Card for one season retrospective on the vertical timeline. */
function RetrospectiveCard({ retro }: { retro: SeasonRetrospective }) {
  return (
    <li className="relative">
      <span
        aria-hidden="true"
        className="absolute top-1.5 -left-[27px] h-3 w-3 rounded-full bg-ink ring-4 ring-white"
      />
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
        <h3 className="font-display text-base font-semibold text-ink">
          {retro.season_label ?? "シーズン"}
        </h3>
        {(retro.period_start != null || retro.period_end != null) && (
          <span className="font-numeric text-xs tabular-nums text-slate-400">
            {retro.period_start ?? "?"} 〜 {retro.period_end ?? "?"}
          </span>
        )}
      </div>
      {retro.narrative != null && (
        <p className="mt-1.5 text-sm leading-relaxed whitespace-pre-line text-slate-700">
          {retro.narrative}
        </p>
      )}
      {retro.key_learnings != null && retro.key_learnings.trim() !== "" && (
        <details className="group mt-2 rounded-lg bg-gold/5 px-3 py-2">
          <summary className="flex cursor-pointer list-none items-center gap-2 text-xs font-semibold tracking-wide text-amber-700">
            <span
              aria-hidden="true"
              className="transition-transform group-open:rotate-90"
            >
              ›
            </span>
            学び
          </summary>
          <p className="mt-1.5 text-sm leading-relaxed whitespace-pre-line text-slate-700">
            {retro.key_learnings}
          </p>
        </details>
      )}
    </li>
  );
}

/** Format a signed gap in seconds as ±H:MM:SS / ±M:SS (0 -> "±0:00"). */
export function formatGap(seconds: number): string {
  const sign = seconds > 0 ? "+" : seconds < 0 ? "−" : "±";
  const abs = Math.abs(seconds);
  const hours = Math.floor(abs / 3600);
  const minutes = Math.floor((abs % 3600) / 60);
  const secs = abs % 60;
  const body =
    hours > 0
      ? `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`
      : `${minutes}:${String(secs).padStart(2, "0")}`;
  return `${sign}${body}`;
}

type RaceStatus = NonNullable<RaceReadiness["progress"]>["status"];

const STATUS_META: Record<RaceStatus, { label: string; tone: StatusTone }> = {
  ahead: { label: "前倒し", tone: "good" },
  on_track: { label: "順調", tone: "info" },
  behind: { label: "遅れ", tone: "warn" },
};

/**
 * Race prediction card: current VDOT, the goal-distance predicted time, the gap
 * to target, and a status badge. Falls back to an explanatory line when VDOT or
 * the goal is missing.
 */
function RacePredictionCard({ readiness }: { readiness: RaceReadiness }) {
  const { current_vdot, goal, progress } = readiness;

  if (current_vdot == null) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <EmptyState
          message="現在のフィットネスを推定できませんでした"
          hint="直近のランニングデータが不足しています"
        />
      </div>
    );
  }

  const weeksRemaining = progress?.weeks_remaining ?? null;
  const statusMeta = progress != null ? STATUS_META[progress.status] : null;

  return (
    <article className="relative overflow-hidden rounded-xl border border-signal/40 bg-white p-5 shadow-sm ring-1 ring-signal/20">
      <span
        aria-hidden="true"
        className="absolute inset-y-0 left-0 w-1 bg-signal"
      />
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-display text-lg font-semibold text-ink">
            {goal?.race_name ?? "目標レース未設定"}
          </h3>
          {weeksRemaining != null && (
            <p className="mt-0.5 font-numeric text-sm tabular-nums text-slate-500">
              残り {weeksRemaining} 週
            </p>
          )}
        </div>
        {statusMeta != null && (
          <StatusBadge tone={statusMeta.tone}>{statusMeta.label}</StatusBadge>
        )}
      </div>

      <dl className="mt-4 grid grid-cols-3 gap-3 border-t border-slate-100 pt-4">
        <div>
          <dt className="text-xs tracking-wide text-slate-400">現在 VDOT</dt>
          <dd className="mt-0.5 font-numeric text-base font-semibold tabular-nums text-ink">
            {current_vdot.toFixed(1)}
          </dd>
        </div>
        <div>
          <dt className="text-xs tracking-wide text-slate-400">予測タイム</dt>
          <dd className="mt-0.5 font-numeric text-base font-semibold tabular-nums text-ink">
            {progress != null
              ? formatTargetTime(progress.predicted_time_seconds)
              : "-"}
          </dd>
        </div>
        <div>
          <dt className="text-xs tracking-wide text-slate-400">目標との差</dt>
          <dd className="mt-0.5 font-numeric text-base font-semibold tabular-nums text-ink">
            {progress != null ? formatGap(progress.gap_seconds) : "-"}
          </dd>
        </div>
      </dl>

      {goal != null && goal.target_time_seconds != null && (
        <p className="mt-4 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600">
          目標タイム {formatTargetTime(goal.target_time_seconds)} に対する現在の予測です。
        </p>
      )}
      {goal == null && (
        <p className="mt-4 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600">
          目標レースが未登録のため、距離別の予測タイムのみ算出しています。
        </p>
      )}
    </article>
  );
}

export default function Goal() {
  const goalQuery = useGoal();
  // Race readiness is supplementary: a failure here must not block the page,
  // so its error is ignored and the prediction card is simply hidden.
  const readinessQuery = useRaceReadiness();

  const goal = goalQuery.data ?? null;
  const readiness = readinessQuery.data ?? null;
  const loading = goalQuery.isPending;
  const error = goalQuery.error;

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
        エラー: {error.message}
      </p>
    );
  }
  if (goal == null) {
    return null;
  }

  const { profile, goals, retrospectives } = goal;
  const hasProfile =
    profile.current_focus != null || profile.focus_notes != null;
  const focusSections = parseFocusNotes(profile.focus_notes);
  // The hero headlines the first priority-A and first priority-B race; those
  // same races are de-emphasized in the list below to avoid double-featuring.
  const heroRaceIds = new Set(
    [goals.find(isPriorityA), goals.find(isPriorityB)]
      .filter((race): race is GoalRace => race != null)
      .map((race) => race.goal_id),
  );
  const hasFeaturedRace = heroRaceIds.size > 0;

  return (
    <div className="stagger-in space-y-8">
      {/* 1. Race countdown hero */}
      {hasFeaturedRace && <CountdownHero goals={goals} />}

      {/* 1b. Race prediction (VDOT-based gap to the goal) */}
      {readiness != null && (
        <section className="space-y-4">
          <SectionHeading eyebrow="Race prediction" title="レース予測" as="h2" />
          <RacePredictionCard readiness={readiness} />
        </section>
      )}

      {/* 2. Target races as cards */}
      <section className="space-y-4">
        <SectionHeading eyebrow="Target races" title="目標レース" as="h2" />
        {goals.length > 0 ? (
          <div className="grid gap-4 md:grid-cols-2">
            {goals.map((race) => (
              <RaceCard
                key={race.goal_id}
                race={race}
                deemphasizeFeatured={heroRaceIds.has(race.goal_id)}
              />
            ))}
          </div>
        ) : (
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <EmptyState
              message="目標レースが登録されていません"
              hint={
                <>
                  CLI <CliCommand>/set-goal</CliCommand> で登録できます
                </>
              }
            />
          </div>
        )}
      </section>

      {/* 3. Current phase as a structured accordion */}
      <section className="space-y-4">
        <SectionHeading eyebrow="Current phase" title="現フェーズ" as="h2" />
        {hasProfile ? (
          <div className="space-y-3">
            {profile.current_focus != null && (
              <p className="border-l-4 border-signal pl-4 font-display text-lg leading-snug font-semibold text-ink">
                {profile.current_focus}
              </p>
            )}
            {focusSections.length > 0 && (
              <div className="space-y-2">
                {focusSections.map((section, i) => (
                  <FocusSectionCard
                    // Sections are positional and have no stable id.
                    // eslint-disable-next-line react/no-array-index-key
                    key={i}
                    title={section.title}
                    body={section.body}
                    defaultOpen={section.title == null || i < 3}
                  />
                ))}
              </div>
            )}
            {profile.updated_at != null && (
              <p className="text-xs text-slate-400">更新: {profile.updated_at}</p>
            )}
          </div>
        ) : (
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <EmptyState
              message="現フェーズが登録されていません"
              hint={
                <>
                  CLI <CliCommand>/set-goal</CliCommand> で登録できます
                </>
              }
            />
          </div>
        )}
      </section>

      {/* 4. Season retrospectives as a timeline */}
      <section className="space-y-4">
        <SectionHeading eyebrow="Retrospective" title="昨季の振り返り" as="h2" />
        {retrospectives.length > 0 ? (
          <ol className="relative ml-1.5 space-y-6 border-l-2 border-slate-200 pl-6">
            {retrospectives.map((retro) => (
              <RetrospectiveCard key={retro.retro_id} retro={retro} />
            ))}
          </ol>
        ) : (
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <EmptyState
              message="振り返りが登録されていません"
              hint={
                <>
                  CLI <CliCommand>/set-goal</CliCommand> で登録できます
                </>
              }
            />
          </div>
        )}
      </section>
    </div>
  );
}
