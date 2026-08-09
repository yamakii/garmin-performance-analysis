import { CARD_CLASS } from "../components/Card";
import Disclosure from "../components/Disclosure";
import EmptyState, { CliCommand } from "../components/EmptyState";
import { PageError, PageLoading } from "../components/PageState";
import SectionHeading from "../components/SectionHeading";
import StatusBadge, { type StatusTone } from "../components/StatusBadge";
import { useGoal, useRaceReadiness } from "../api/hooks";
import { usePageTitle } from "../hooks/usePageTitle";
import type {
  GoalRace,
  RaceReadiness,
  RaceReadinessProgress,
  SeasonRetrospective,
} from "../types";
import { parseFocusNotes } from "../utils/focusNotes";
import { daysUntil, formatGap, formatTargetTime } from "../utils/race";

function formatDistanceKm(km: number | null): string {
  if (km == null) {
    return "-";
  }
  return `${km.toFixed(2)} km`;
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

type RaceStatus = RaceReadinessProgress["status"];

const STATUS_META: Record<RaceStatus, { label: string; tone: StatusTone }> = {
  ahead: { label: "前倒し", tone: "good" },
  on_track: { label: "順調", tone: "info" },
  behind: { label: "遅れ", tone: "warn" },
};

/**
 * Single "あと N日" countdown tile inside the hero. When the VDOT prediction
 * belongs to this race, the predicted time / gap to target / status badge are
 * rendered inline here rather than in a second card further down the page.
 */
function CountdownTile({
  race,
  tone,
  prediction,
}: {
  race: GoalRace;
  tone: "primary" | "secondary";
  prediction: RaceReadinessProgress | null;
}) {
  const days = daysUntil(race.race_date);
  // The countdown numeral is 6xl/7xl bold — large text, so the vivid signal
  // orange still clears the 3:1 large-text threshold. Gold does not (2.15:1),
  // so the B race uses amber-700 (5.05:1). The A/B tags are small text and
  // take the text-safe `signal-ink` / amber-800 pair instead (Issue #911).
  const accent = tone === "primary" ? "text-signal" : "text-amber-700";
  const tagBg =
    tone === "primary"
      ? "bg-signal/15 text-signal-ink"
      : "bg-gold/15 text-amber-800";
  const statusMeta = prediction != null ? STATUS_META[prediction.status] : null;

  return (
    <div className="relative">
      <div className="flex items-start justify-between gap-3">
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
        {statusMeta != null && (
          <StatusBadge tone={statusMeta.tone}>{statusMeta.label}</StatusBadge>
        )}
      </div>

      <div className="mt-3 flex items-end gap-2">
        {days == null ? (
          <span className="rounded-md bg-slate-100 px-3 py-1.5 font-display text-sm font-medium text-slate-600">
            日程未定
          </span>
        ) : days >= 0 ? (
          <>
            <span className="font-display text-xs font-medium tracking-wide text-slate-600">
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
          <span className="rounded-md bg-slate-100 px-3 py-1.5 font-display text-sm font-medium text-slate-600">
            開催済み
          </span>
        )}
      </div>

      {/*
       * Muted copy inside the hero is slate-600, not the slate-500 used on the
       * white cards below: this band is `from-white via-slate-50
       * to-slate-100`, and slate-500 slips to 4.35:1 at the slate-100 end
       * (Issue #911). Uniform here so the unit suffix never outweighs the
       * value it trails.
       */}
      <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-sm">
        {race.race_date != null && (
          <div>
            <dt className="sr-only">開催日</dt>
            <dd className="font-numeric tabular-nums text-slate-600">
              {race.race_date}
            </dd>
          </div>
        )}
        <div>
          <dt className="sr-only">種別</dt>
          <dd className="text-slate-600">
            {goalTypeLabel(race.goal_type)}
            {race.distance_km != null && (
              <span className="ml-1.5 font-numeric tabular-nums text-slate-600">
                {formatDistanceKm(race.distance_km)}
              </span>
            )}
          </dd>
        </div>
        <div>
          <dt className="sr-only">目標タイム</dt>
          <dd>
            <span className="text-xs text-slate-600">目標 </span>
            <span className="font-numeric text-lg font-semibold tabular-nums text-ink">
              {formatTargetTime(race.target_time_seconds)}
            </span>
          </dd>
        </div>
      </dl>

      {race.notes != null && race.notes.trim() !== "" && (
        <p className="mt-3 text-sm text-slate-600">{race.notes}</p>
      )}

      {prediction != null && (
        <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-slate-200 pt-3">
          <div>
            <dt className="text-xs tracking-wide text-slate-600">予測タイム</dt>
            <dd className="mt-0.5 font-numeric text-base font-semibold tabular-nums text-ink">
              {formatTargetTime(prediction.predicted_time_seconds)}
            </dd>
          </div>
          <div>
            <dt className="text-xs tracking-wide text-slate-600">目標との差</dt>
            <dd className="mt-0.5 font-numeric text-base font-semibold tabular-nums text-ink">
              {formatGap(prediction.gap_seconds)}
            </dd>
          </div>
        </dl>
      )}
    </div>
  );
}

/**
 * Which featured race the readiness prediction belongs to. The API computes
 * readiness against a single goal race, so the prediction is attached to the
 * tile whose name matches; when the payload carries no usable name we fall back
 * to the primary (A) race so the prediction is never orphaned.
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
 * Hero band with countdowns to the A (primary) and B (secondary) races, with
 * the VDOT prediction folded into the matching tile. These races are the only
 * place the A/B races are featured — the list below covers everything else.
 */
function CountdownHero({
  races,
  readiness,
}: {
  races: GoalRace[];
  readiness: RaceReadiness | null;
}) {
  const vdot = readiness?.current_vdot ?? null;

  if (races.length === 0 && vdot == null) {
    return null;
  }

  const predictionRace = findPredictionRace(races, readiness);
  const progress = readiness?.progress ?? null;

  return (
    <header className="relative overflow-hidden rounded-2xl border border-slate-200 bg-gradient-to-br from-white via-slate-50 to-slate-100 shadow-sm">
      <div
        aria-hidden="true"
        className="absolute inset-0 opacity-[0.04]"
        style={{ backgroundImage: CONTOUR_PATTERN }}
      />
      <div className="relative px-6 py-7 md:px-8">
        <SectionHeading
          eyebrow="Countdown"
          title={races.length > 0 ? "目標レースまで" : "現在のフィットネス"}
        />
        {races.length > 0 && (
          <div className="mt-6 grid gap-8 md:grid-cols-2 md:gap-12">
            {races.map((race) => (
              <CountdownTile
                key={race.goal_id}
                race={race}
                tone={isPriorityA(race) ? "primary" : "secondary"}
                prediction={
                  race.goal_id === predictionRace?.goal_id ? progress : null
                }
              />
            ))}
          </div>
        )}

        {vdot != null && (
          <div className="mt-6 border-t border-slate-200 pt-4">
            <dl className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
              <div>
                <dt className="inline text-xs text-slate-600">現在 VDOT </dt>
                <dd className="inline font-numeric font-semibold tabular-nums text-ink">
                  {vdot.toFixed(1)}
                </dd>
              </div>
            </dl>
            {races.length === 0 && (
              <p className="mt-1.5 text-xs text-slate-500">
                目標レースが未登録のため、距離別の予測タイムのみ算出しています。
              </p>
            )}
          </div>
        )}
        {vdot == null && readiness != null && (
          <p className="mt-6 border-t border-slate-200 pt-4 text-xs text-slate-500">
            直近のランニングデータが不足しているため、予測タイムは算出できませんでした。
          </p>
        )}
      </div>
    </header>
  );
}

/**
 * Card for one registered race. The hero already headlines the first A and B
 * races, so this list only ever receives the remaining races; a leftover
 * priority-A race (a second A) still gets the featured treatment.
 */
function RaceCard({ race }: { race: GoalRace }) {
  const featured = isPriorityA(race);
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
              featured ? "bg-signal/15 text-signal-ink" : "bg-ink/5 text-ink"
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
          <dt className="text-xs tracking-wide text-slate-500">種別</dt>
          <dd className="mt-0.5 text-sm font-medium text-slate-700">
            {goalTypeLabel(race.goal_type)}
          </dd>
        </div>
        <div>
          <dt className="text-xs tracking-wide text-slate-500">距離</dt>
          <dd className="mt-0.5 font-numeric text-sm tabular-nums text-slate-700">
            {formatDistanceKm(race.distance_km)}
          </dd>
        </div>
        <div>
          <dt className="text-xs tracking-wide text-slate-500">目標タイム</dt>
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
 * paragraph; titled sections render as a shared `Disclosure` card. The first
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
    <Disclosure
      defaultOpen={defaultOpen}
      title={
        <>
          <span
            aria-hidden="true"
            className="h-3 w-3 shrink-0 rounded-full bg-signal/70"
          />
          {title}
        </>
      }
    >
      <p className="text-sm leading-relaxed whitespace-pre-line text-slate-600">
        {body}
      </p>
    </Disclosure>
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
          <span className="font-numeric text-xs tabular-nums text-slate-500">
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
        <Disclosure
          className="mt-2"
          title={
            <span className="tracking-wide text-amber-700">学び</span>
          }
        >
          <p className="text-sm leading-relaxed whitespace-pre-line text-slate-700">
            {retro.key_learnings}
          </p>
        </Disclosure>
      )}
    </li>
  );
}

export default function Goal() {
  usePageTitle("目標");
  const goalQuery = useGoal();
  // Race readiness is supplementary: a failure here must not block the page,
  // so its error is ignored and the hero simply omits the prediction.
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
      <div className="stagger-in space-y-6">
        <SectionHeading eyebrow="Goal" title="目標" />
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
  // The hero headlines the first priority-A and first priority-B race (with the
  // VDOT prediction folded in); the list below carries every other race, so no
  // race is featured twice on the page.
  const featuredRaces = [
    goals.find(isPriorityA),
    goals.find(isPriorityB),
  ].filter((race): race is GoalRace => race != null);
  const featuredIds = new Set(featuredRaces.map((race) => race.goal_id));
  const otherRaces = goals.filter((race) => !featuredIds.has(race.goal_id));
  // The hero carries this page's only h1, and it renders nothing when there is
  // neither a featured race nor a VDOT — which left the empty page headless
  // under a run of h2 sections (#912). Mirrors CountdownHero's own guard.
  const hasHero =
    featuredRaces.length > 0 || readiness?.current_vdot != null;

  return (
    <div className="stagger-in space-y-8">
      {/* 1. Race countdown + VDOT prediction */}
      {hasHero ? (
        <CountdownHero races={featuredRaces} readiness={readiness} />
      ) : (
        <SectionHeading eyebrow="Goal" title="目標" />
      )}

      {/* 2. Current phase as a structured accordion */}
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
              <p className="text-xs text-slate-500">更新: {profile.updated_at}</p>
            )}
          </div>
        ) : (
          <div className={CARD_CLASS}>
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

      {/* 3. Registered races (everything the hero does not headline) */}
      <section className="space-y-4">
        <SectionHeading eyebrow="Races" title="レース登録" as="h2" />
        {featuredRaces.length > 0 && (
          <p className="text-xs text-slate-500">
            A / B レースはページ上部のカウントダウンに表示しています。
          </p>
        )}
        {otherRaces.length > 0 ? (
          <div className="grid gap-4 md:grid-cols-2">
            {otherRaces.map((race) => (
              <RaceCard key={race.goal_id} race={race} />
            ))}
          </div>
        ) : (
          <div className={CARD_CLASS}>
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
          <div className={CARD_CLASS}>
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
