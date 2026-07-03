import { useState } from "react";
import { useTrendNarration, useTrendNarrationVersions } from "../api/hooks";
import type { Granularity, TrendNarration } from "../api/trends";

/**
 * Full-width coach-narration card for the Trends dashboard (#791).
 *
 * Reads the latest longitudinal trend narration for the current granularity,
 * then loads every saved version of that period so the reader can switch
 * between past write-ups (modeled on `WeeklyReviewDetail`'s `版を選択:` select).
 * The free-form `analysis_data` payload is rendered as prose: string values
 * become paragraphs and string arrays become bullet lists. Renders nothing
 * until a narration exists (a 404 / empty table simply hides the card).
 */

interface TrendNarrationCardProps {
  granularity: Granularity;
}

function versionLabel(version: TrendNarration, isLatest: boolean): string {
  const stamp = version.created_at ?? "日時不明";
  return isLatest ? `${stamp}（最新）` : stamp;
}

function NarrativeBody({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data);
  return (
    <div className="space-y-3 text-sm leading-relaxed text-slate-700">
      {entries.map(([key, value]) => {
        if (typeof value === "string") {
          const lines = value.split("\n").filter((line) => line.trim() !== "");
          return (
            <div key={key} className="space-y-1">
              {lines.map((line, i) => (
                <p key={i}>{line}</p>
              ))}
            </div>
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

  // No narration saved yet (404 / empty) — hide the card entirely.
  if (selected == null) {
    return null;
  }

  const label = granularity === "month" ? "月次トレンド" : "週次トレンド";

  return (
    <section
      aria-label="トレンド解説"
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-display text-base font-semibold text-ink">
          トレンド解説
        </h2>
        <span className="font-numeric text-sm tabular-nums text-slate-500">
          {label}: {selected.period_start} 〜 {selected.period_end}
        </span>
      </div>

      {versions.length > 1 && (
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <label
            htmlFor="trend-narration-version-select"
            className="text-sm font-medium text-slate-500"
          >
            版を選択:
          </label>
          <select
            id="trend-narration-version-select"
            value={selectedIndex}
            onChange={(e) => setSelectedIndex(Number(e.target.value))}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-ink shadow-sm focus:border-ink focus:outline-none"
          >
            {versions.map((v, i) => (
              <option key={v.created_at ?? i} value={i}>
                {versionLabel(v, i === 0)}
              </option>
            ))}
          </select>
          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">
            全{versions.length}版
          </span>
        </div>
      )}

      <NarrativeBody data={selected.analysis_data} />
    </section>
  );
}
