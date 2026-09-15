import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useActivities, type ActivityRange } from "../api/hooks";
import EmptyState from "../components/EmptyState";
import { PageError, PageLoading } from "../components/PageState";
import SectionHeading from "../components/SectionHeading";
import { usePageTitle } from "../hooks/usePageTitle";
import type { ActivitySummary } from "../types";
import {
  formatBpmValue,
  formatDate,
  formatDistanceKm,
  formatDistanceKmValue,
  formatPaceValue,
  toIsoDate,
} from "../utils/format";

/** "N本 ・ 合計 XX.X km" summary for a month heading (Issue #214). */
export function monthSummary(activities: ActivitySummary[]): string {
  const totalKm = activities.reduce(
    (sum, activity) => sum + (activity.total_distance_km ?? 0),
    0,
  );
  return `${activities.length}本 ・ 合計 ${formatDistanceKm(totalKm, 1)}`;
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
    ? `${base} text-ink`
    : `${base} text-ink-muted hover:text-ink`;
}

export default function ActivityList() {
  usePageTitle("アクティビティ一覧");
  // The filter state lives in the URL so it survives a reload, a back
  // navigation and a bookmark — nothing is mirrored in component state.
  const [searchParams, setSearchParams] = useSearchParams();
  const preset = parsePreset(searchParams.get("range"));
  const search = searchParams.get("q") ?? "";

  // The date range is a server-side bound (fewer rows over the wire); the text
  // query filters what came back, so typing never triggers a refetch.
  const range = useMemo(() => presetToRange(preset), [preset]);
  const { data, isPending, error, refetch } = useActivities(range);
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
        <SectionHeading title="アクティビティ一覧" />
      </div>

      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div
          role="group"
          aria-label="期間"
          className="inline-flex rounded-md border border-hairline bg-well p-0.5"
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
          className="w-full rounded-md border border-hairline px-3 py-1.5 text-sm text-ink transition-colors focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent sm:w-64"
        />
      </div>

      {isPending ? (
        <PageLoading />
      ) : error ? (
        <PageError error={error} onRetry={() => void refetch()} />
      ) : visible.length === 0 ? (
        <div className="rounded-md border border-hairline px-4 py-8">
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
                  className="cursor-pointer font-medium text-accent underline underline-offset-2 hover:text-ink"
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
            <h2 className="mb-2 flex items-baseline gap-3 text-sm font-semibold text-ink-muted">
              <span className="font-mono text-base text-ink">{month}</span>
              <span className="font-normal">
                {monthSummary(monthActivities)}
              </span>
            </h2>
            <ul className="space-y-2">
              {monthActivities.map((activity) => (
                <li key={activity.activity_id}>
                  <Link
                    to={`/activities/${activity.activity_id}`}
                    className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md border border-hairline px-4 py-3 transition-[box-,border-color] hover:border-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent sm:flex-nowrap"
                  >
                    <span className="shrink-0 rounded-md bg-well px-2 py-1 font-mono text-sm font-semibold text-ink">
                      {formatDate(activity.activity_date)}
                    </span>
                    {/*
                      Below `sm` the date + metrics already fill the row, so the
                      name is pushed onto its own second line instead of being
                      squeezed to 0px (#1145). From `sm` up it is the middle
                      column again.
                    */}
                    <span className="order-last min-w-0 basis-full truncate text-sm font-medium text-ink-soft sm:order-none sm:flex-1 sm:basis-auto">
                      {activity.activity_name ?? "-"}
                    </span>
                    <span className="flex shrink-0 items-baseline divide-x divide-hairline text-right font-mono text-ink-soft">
                      <span className="pr-3">
                        <span className="text-base font-semibold text-ink-soft">
                          {formatDistanceKmValue(activity.total_distance_km)}
                        </span>
                        <span className="ml-0.5 text-xs font-normal text-ink-muted">
                          km
                        </span>
                      </span>
                      <span className="px-3">
                        <span className="text-base">
                          {formatPaceValue(activity.avg_pace_seconds_per_km)}
                        </span>
                        <span className="ml-0.5 text-xs text-ink-muted">
                          /km
                        </span>
                      </span>
                      <span className="pl-3">
                        <span className="text-base">
                          {formatBpmValue(activity.avg_heart_rate)}
                        </span>
                        <span className="ml-0.5 text-xs text-ink-muted">
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
