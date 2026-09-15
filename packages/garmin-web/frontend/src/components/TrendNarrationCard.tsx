import { useState } from "react";
import { useTrendNarration, useTrendNarrationVersions } from "../api/hooks";
import type { Granularity, TrendNarration } from "../api/trends";
import CardSkeleton from "./CardSkeleton";
import Disclosure from "./Disclosure";
import VersionSelect from "./VersionSelect";

/**
 * The coach's longitudinal write-up, folded away (#791, restyled in #1121).
 *
 * `/performance` now opens with the verdict and the narration's first
 * paragraph as its lead (see {@link narrationLead}); the rest of the write-up —
 * and the picker for past versions of it — lives behind this disclosure, so the
 * page leads with the judgement instead of a wall of prose. The free-form
 * `analysis_data` payload is rendered as it comes: string values become
 * paragraphs, string arrays become bullet lists. Renders nothing until a
 * narration exists (a 404 / empty table simply hides it).
 */

interface TrendNarrationCardProps {
  granularity: Granularity;
}

/** The disclosure's trigger; the arrow is appended by `Disclosure`. */
const FULL_TEXT_LABEL = "コーチ解説の全文";

/**
 * The narration's opening paragraph — the one sentence-or-two the page uses as
 * the rationale under its verdict.
 *
 * The payload is free-form, so the lead is the first non-empty string value in
 * it, cut at its first line break: these write-ups are stored one paragraph per
 * line, and the opening paragraph is the summary the coach wrote first.
 */
export function narrationLead(narration: TrendNarration): string {
  for (const value of Object.values(narration.analysis_data)) {
    if (typeof value !== "string") {
      continue;
    }
    const paragraph = value
      .split(/\n+/)
      .map((part) => part.trim())
      .find((part) => part !== "");
    if (paragraph != null) {
      return paragraph;
    }
  }
  return "";
}

function NarrativeBody({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data);
  return (
    <div className="flex flex-col gap-3 text-[15px] leading-[1.7] text-ink-soft">
      {entries.map(([key, value]) => {
        if (typeof value === "string") {
          return (
            <p key={key} className="whitespace-pre-line">
              {value}
            </p>
          );
        }
        if (
          Array.isArray(value) &&
          value.every((item) => typeof item === "string")
        ) {
          return (
            <ul key={key} className="list-disc space-y-1 pl-5 text-ink-muted">
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

  // Still fetching: hold the space with a skeleton instead of rendering
  // nothing, so the blocks below do not jump when the narration lands (a
  // pending fetch is indistinguishable from "no narration" otherwise).
  if (narrationQuery.isPending) {
    return <CardSkeleton label="トレンド解説" />;
  }

  // No narration saved yet (404 / empty) — hide it entirely.
  if (selected == null) {
    return null;
  }

  return (
    <section aria-label="トレンド解説">
      <Disclosure title={FULL_TEXT_LABEL}>
        <div className="flex flex-col gap-4">
          {versions.length > 1 && (
            <VersionSelect
              id="trend-narration-version-select"
              options={versions.map((v, i) => ({
                key: v.created_at ?? String(i),
                stamp: v.created_at,
              }))}
              selectedIndex={selectedIndex}
              onSelect={setSelectedIndex}
            />
          )}
          <NarrativeBody data={selected.analysis_data} />
        </div>
      </Disclosure>
    </section>
  );
}
