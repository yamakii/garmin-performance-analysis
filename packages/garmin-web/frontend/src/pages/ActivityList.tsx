import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useActivities, type ActivityRange } from "../api/hooks";
import EmptyState from "../components/EmptyState";
import SectionHeading from "../components/SectionHeading";
import type { ActivitySummary } from "../types";

export function formatPace(secondsPerKm: number | null): string {
  if (secondsPerKm == null || secondsPerKm <= 0) {
    return "-";
  }
  let minutes = Math.floor(secondsPerKm / 60);
  let seconds = Math.round(secondsPerKm % 60);
  if (seconds === 60) {
    minutes += 1;
    seconds = 0;
  }
  return `${minutes}:${String(seconds).padStart(2, "0")}/km`;
}

export function formatDistance(km: number | null): string {
  if (km == null) {
    return "-";
  }
  return `${km.toFixed(2)} km`;
}

export function formatCadence(cadence: number | null): string {
  if (cadence == null) {
    return "-";
  }
  return String(Math.round(cadence));
}

/** "N本 ・ 合計 XX.X km" summary for a month heading (Issue #214). */
export function monthSummary(activities: ActivitySummary[]): string {
  const totalKm = activities.reduce(
    (sum, activity) => sum + (activity.total_distance_km ?? 0),
    0,
  );
  return `${activities.length}本 ・ 合計 ${totalKm.toFixed(1)} km`;
}

function groupByMonth(
  activities: ActivitySummary[],
): Map<string, ActivitySummary[]> {
  const groups = new Map<string, ActivitySummary[]>();
  for (const activity of activities) {
    const month = activity.activity_date.slice(0, 7); // YYYY-MM
    const group = groups.get(month);
    if (group) {
      group.push(activity);
    } else {
      groups.set(month, [activity]);
    }
  }
  return groups;
}

/** Lookback window of each range preset, in days counted back from today. */
const PRESET_DAYS = {
  "4w": 28,
  "3m": 92,
  "1y": 365,
  all: null,
} as const;

export type RangePreset = keyof typeof PRESET_DAYS;

/** No range param in the URL means "no date bound" — the historical behaviour. */
const DEFAULT_PRESET: RangePreset = "all";

const PRESETS: { value: RangePreset; label: string }[] = [
  { value: "4w", label: "直近4週" },
  { value: "3m", label: "直近3ヶ月" },
  { value: "1y", label: "直近1年" },
  { value: "all", label: "全期間" },
];

function toIsoDate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

/**
 * Turn a preset into the API's inclusive `from` bound, counted back from
 * `today` in local time (activity dates are local calendar days). "all" maps
 * to an empty range so the request stays unbounded.
 */
export function presetToRange(
  preset: RangePreset,
  today: Date = new Date(),
): ActivityRange {
  const days = PRESET_DAYS[preset];
  if (days == null) {
    return {};
  }
  const from = new Date(today);
  from.setDate(from.getDate() - days);
  return { from: toIsoDate(from) };
}

/** Read the `range` search param, falling back to the default on junk input. */
export function parsePreset(raw: string | null): RangePreset {
  return raw != null && raw in PRESET_DAYS
    ? (raw as RangePreset)
    : DEFAULT_PRESET;
}

/**
 * Case-insensitive substring match on the activity name. Applied to the rows
 * already fetched, so typing narrows the list without another round-trip.
 */
export function filterByName(
  activities: ActivitySummary[],
  query: string,
): ActivitySummary[] {
  const needle = query.trim().toLowerCase();
  if (needle === "") {
    return activities;
  }
  return activities.filter((activity) =>
    (activity.activity_name ?? "").toLowerCase().includes(needle),
  );
}

function toggleClass(active: boolean): string {
  const base =
    "rounded-md px-3 py-1 text-sm font-medium transition-colors cursor-pointer";
  return active
    ? `${base} bg-white text-ink shadow-sm`
    : `${base} text-slate-600 hover:text-ink`;
}

export default function ActivityList() {
  // The filter state lives in the URL so it survives a reload, a back
  // navigation and a bookmark — nothing is mirrored in component state.
  const [searchParams, setSearchParams] = useSearchParams();
  const preset = parsePreset(searchParams.get("range"));
  const search = searchParams.get("q") ?? "";

  // The date range is a server-side bound (fewer rows over the wire); the text
  // query filters what came back, so typing never triggers a refetch.
  const range = useMemo(() => presetToRange(preset), [preset]);
  const { data, isPending, error } = useActivities(range);
  const activities = data ?? [];
  const visible = filterByName(activities, search);
  const isFiltered = preset !== DEFAULT_PRESET || search.trim() !== "";

  function updateParams(
    next: { range?: RangePreset; q?: string },
    options?: { replace?: boolean },
  ) {
    const params = new URLSearchParams(searchParams);
    if (next.range !== undefined) {
      if (next.range === DEFAULT_PRESET) {
        params.delete("range");
      } else {
        params.set("range", next.range);
      }
    }
    if (next.q !== undefined) {
      if (next.q === "") {
        params.delete("q");
      } else {
        params.set("q", next.q);
      }
    }
    setSearchParams(params, options);
  }

  const groups = groupByMonth(visible);

  return (
    <div>
      <div className="mb-6">
        <SectionHeading eyebrow="Activities" title="アクティビティ一覧" />
      </div>

      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div
          role="group"
          aria-label="期間"
          className="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-0.5"
        >
          {PRESETS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              aria-pressed={preset === value}
              className={toggleClass(preset === value)}
              // A preset change is a navigation step: pushed, so "back"
              // returns to the previous range.
              onClick={() => updateParams({ range: value })}
            >
              {label}
            </button>
          ))}
        </div>
        <input
          type="search"
          value={search}
          aria-label="アクティビティ名で検索"
          placeholder="アクティビティ名で検索"
          // Typing replaces the entry instead of pushing one per keystroke,
          // so "back" does not walk character by character.
          onChange={(event) =>
            updateParams({ q: event.target.value }, { replace: true })
          }
          className="w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-ink shadow-sm transition-colors focus-visible:border-signal/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal/50 sm:w-64"
        />
      </div>

      {isPending ? (
        <div className="flex items-center justify-center gap-3 py-16 text-sm text-slate-500">
          <span
            aria-hidden="true"
            className="h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-ink"
          />
          読み込み中...
        </div>
      ) : error ? (
        <p
          role="alert"
          className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
        >
          エラー: {error.message}
        </p>
      ) : visible.length === 0 ? (
        <div className="rounded-xl border border-slate-200 bg-white px-4 py-8 shadow-sm">
          <EmptyState
            message={
              isFiltered
                ? "条件に一致するアクティビティがありません"
                : "アクティビティがありません"
            }
            hint={
              isFiltered ? (
                <button
                  type="button"
                  onClick={() =>
                    updateParams({ range: DEFAULT_PRESET, q: "" })
                  }
                  className="cursor-pointer font-medium text-signal-ink underline underline-offset-2 hover:text-ink"
                >
                  フィルタを解除
                </button>
              ) : undefined
            }
          />
        </div>
      ) : (
        [...groups.entries()].map(([month, monthActivities]) => (
          <section key={month} className="mb-8">
            <h2 className="mb-2 flex items-baseline gap-3 text-sm font-semibold text-slate-500">
              <span className="font-numeric text-base text-ink">{month}</span>
              <span className="font-normal">
                {monthSummary(monthActivities)}
              </span>
            </h2>
            <ul className="stagger-in space-y-2">
              {monthActivities.map((activity) => (
                <li key={activity.activity_id}>
                  <Link
                    to={`/activities/${activity.activity_id}`}
                    className="flex items-center gap-4 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm transition-[box-shadow,border-color] hover:border-signal/50 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal/50"
                  >
                    <span className="shrink-0 rounded-md bg-ink/5 px-2 py-1 font-numeric text-sm font-semibold tabular-nums text-ink">
                      {activity.activity_date}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-sm font-medium text-slate-800">
                      {activity.activity_name ?? "-"}
                    </span>
                    <span className="flex shrink-0 items-baseline divide-x divide-slate-200 text-right font-numeric tabular-nums text-slate-700">
                      <span className="pr-3">
                        <span className="text-base font-semibold text-slate-800">
                          {formatDistance(activity.total_distance_km).replace(
                            " km",
                            "",
                          )}
                        </span>
                        <span className="ml-0.5 text-xs font-normal text-slate-500">
                          km
                        </span>
                      </span>
                      <span className="px-3">
                        <span className="text-base">
                          {formatPace(activity.avg_pace_seconds_per_km).replace(
                            "/km",
                            "",
                          )}
                        </span>
                        <span className="ml-0.5 text-xs text-slate-500">
                          /km
                        </span>
                      </span>
                      <span className="pl-3">
                        <span className="text-base">
                          {activity.avg_heart_rate ?? "-"}
                        </span>
                        <span className="ml-0.5 text-xs text-slate-500">
                          bpm
                        </span>
                      </span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ))
      )}
    </div>
  );
}
