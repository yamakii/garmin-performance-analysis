import { useState } from "react";
import { useTrendNarration, useTrendNarrationVersions } from "../api/hooks";
import type { Granularity } from "../api/trends";
import { formatDate } from "../utils/format";
import { CARD_CLASS } from "./Card";
import CardSkeleton from "./CardSkeleton";
import ClampedProse from "./ClampedProse";
import VersionSelect from "./VersionSelect";

/**
 * Full-width coach-narration card for the Trends dashboard (#791).
 *
 * Reads the latest longitudinal trend narration for the current granularity,
 * then loads every saved version of that period so the reader can switch
 * between past write-ups (modeled on `WeeklyReviewDetail`'s `版を選択:` select).
 * The free-form `analysis_data` payload is rendered as prose: string values
 * become clamped paragraphs (first few lines, with a 続きを読む toggle) and
 * string arrays become bullet lists. Renders nothing until a narration exists
 * (a 404 / empty table simply hides the card).
 */

interface TrendNarrationCardProps {
  granularity: Granularity;
}

/** Default clamp for a narration paragraph: long enough to carry the verdict. */
const NARRATIVE_CLAMP_LINES = 6;

function NarrativeBody({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data);
  return (
    <div className="space-y-3 text-sm leading-relaxed text-slate-700">
      {entries.map(([key, value]) => {
        if (typeof value === "string") {
          return (
            <ClampedProse
              key={key}
              text={value}
              lines={NARRATIVE_CLAMP_LINES}
            />
          );
        }
        if (
          Array.isArray(value) &&
          value.every((item) => typeof item === "string")
        ) {
          return (
            <ul key={key} className="list-disc space-y-1 pl-5 text-slate-600">
              {(value as string[]).map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          );
        }
        return null;
      })}
    </div>
  );
}

export default function TrendNarrationCard({
  granularity,
}: TrendNarrationCardProps) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const narrationQuery = useTrendNarration(granularity);
  const periodStart = narrationQuery.data?.period_start;
  const versionsQuery = useTrendNarrationVersions(granularity, periodStart);

  const versions = versionsQuery.data ?? [];
  const hasVersions = versions.length > 0;
  const selected = hasVersions
    ? versions[Math.min(selectedIndex, versions.length - 1)]
    : narrationQuery.data;

  // Still fetching: hold the card's space with a skeleton instead of rendering
  // nothing, so the surrounding cards do not jump when the narration lands
  // (a pending fetch is indistinguishable from "no narration" otherwise).
  if (narrationQuery.isPending) {
    return <CardSkeleton label="トレンド解説" />;
  }

  // No narration saved yet (404 / empty) — hide the card entirely.
  if (selected == null) {
    return null;
  }

  const label = granularity === "month" ? "月次トレンド" : "週次トレンド";

  return (
    <section
      aria-label="トレンド解説"
      className={CARD_CLASS}
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-display text-base font-semibold text-ink">
          トレンド解説
        </h2>
        <span className="font-numeric text-sm tabular-nums text-slate-500">
          {label}: {formatDate(selected.period_start)} 〜{" "}
          {formatDate(selected.period_end)}
        </span>
      </div>

      {versions.length > 1 && (
        <div className="mb-4">
          <VersionSelect
            id="trend-narration-version-select"
            options={versions.map((v, i) => ({
              key: v.created_at ?? String(i),
              stamp: v.created_at,
            }))}
            selectedIndex={selectedIndex}
            onSelect={setSelectedIndex}
          />
        </div>
      )}

      <NarrativeBody data={selected.analysis_data} />
    </section>
  );
}
