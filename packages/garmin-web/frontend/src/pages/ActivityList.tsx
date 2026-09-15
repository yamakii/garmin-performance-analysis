import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useActivities, type ActivityRange } from "../api/hooks";
import EmptyState from "../components/EmptyState";
import { PageError, PageLoading } from "../components/PageState";
import SectionHeading from "../components/SectionHeading";
import Segment, { type SegmentOption } from "../components/Segment";
import { usePageTitle } from "../hooks/usePageTitle";
import type { ActivitySummary } from "../types";
import {
  formatBpmValue,
  formatDateLabel,
  formatDistanceKm,
  formatDistanceKmValue,
  formatPaceValue,
  toIsoDate,
} from "../utils/format";

/** "N本 · 合計 XX.X km" summary for a month heading (Issue #214). */
export function monthSummary(activities: ActivitySummary[]): string {
  const totalKm = activities.reduce(
    (sum, activity) => sum + (activity.total_distance_km ?? 0),
    0,
  );
  return `${activities.length}本 · 合計 ${formatDistanceKm(totalKm, 1)}`;
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

const PRESETS: SegmentOption<RangePreset>[] = [
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
        {/*
          A preset change is a navigation step: pushed, so "back" returns to
          the previous range.
        */}
        <Segment
          options={PRESETS}
          value={preset}
          onChange={(range) => updateParams({ range })}
          ariaLabel="期間"
        />
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
          className="w-full rounded-sm border border-hairline bg-paper px-3 py-1.5 font-mono text-[13px] text-ink focus-visible:border-ink focus-visible:ring-2 focus-visible:ring-ink focus-visible:outline-none sm:w-64"
        />
      </div>

      {isPending ? (
        <PageLoading />
      ) : error ? (
        <PageError error={error} onRetry={() => void refetch()} />
      ) : visible.length === 0 ? (
        <div className="border border-hairline px-4 py-8">
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
            <h2 className="mb-2 flex items-baseline gap-3 border-b border-ink pb-2">
              <span className="font-mono text-[13px] font-semibold text-ink">
                {month}
              </span>
              <span className="font-mono text-xs text-ink-muted">
                {monthSummary(monthActivities)}
              </span>
            </h2>
            <ul>
              {monthActivities.map((activity) => (
                <li key={activity.activity_id}>
                  {/*
                    A rule row, not a card: the month's runs read as one
                    ledger, and only the hairline under each row separates
                    them (#1185).

                    Below `sm` the date + metrics already fill the row, so the
                    name drops to its own second line spanning both columns
                    instead of being squeezed to 0px (#1145). From `sm` up it
                    is the middle column again.
                  */}
                  <Link
                    to={`/activities/${activity.activity_id}`}
                    className="grid grid-cols-[72px_auto] items-baseline gap-x-4 border-b border-hairline py-3 text-inherit hover:bg-surface hover:no-underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink sm:grid-cols-[72px_minmax(0,1fr)_auto]"
                  >
                    <span className="col-start-1 row-start-1 font-mono text-xs text-ink-muted">
                      {formatDateLabel(activity.activity_date)}
                    </span>
                    <span className="col-span-2 row-start-2 truncate text-sm font-bold text-ink sm:col-span-1 sm:col-start-2 sm:row-start-1">
                      {activity.activity_name ?? "-"}
                    </span>
                    {/*
                      Value and unit stay separate elements (#649): the figure
                      is what the eye scans down the column, the unit is a
                      muted suffix that must not join it into one text run.
                    */}
                    <span className="col-start-2 row-start-1 flex justify-self-end gap-4 font-mono text-sm text-ink sm:col-start-3">
                      <span>
                        <span>
                          {formatDistanceKmValue(activity.total_distance_km)}
                        </span>
                        <span className="ml-[3px] text-xs text-ink-muted">
                          km
                        </span>
                      </span>
                      <span>
                        <span>
                          {formatPaceValue(activity.avg_pace_seconds_per_km)}
                        </span>
                        <span className="ml-[3px] text-xs text-ink-muted">
                          /km
                        </span>
                      </span>
                      <span>
                        <span>{formatBpmValue(activity.avg_heart_rate)}</span>
                        <span className="ml-[3px] text-xs text-ink-muted">
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
