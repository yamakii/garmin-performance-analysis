import StatusBadge from "./StatusBadge";
import { formatDateTime } from "../utils/format";

/** One saved version: a stable React key plus its creation stamp. */
export interface VersionOption {
  key: string;
  /** ISO date or datetime the version was written; null when unrecorded. */
  stamp: string | null;
}

interface VersionSelectProps {
  /** DOM id, so each page's select keeps its own label association. */
  id: string;
  /** Versions newest-first — index 0 is the current one. */
  options: VersionOption[];
  selectedIndex: number;
  onSelect: (index: number) => void;
}

/** Shown when a version has no recorded timestamp. */
const NO_STAMP = "日時不明";

/** The one label every version picker uses (Issue #915). */
export const VERSION_SELECT_LABEL = "版を選択:";

/** Warns that the page is not showing the current analysis. */
export const STALE_VERSION_BADGE = "旧版を表示中";

/**
 * Version picker shared by the activity report, the weekly review and the
 * trend narration (Issue #915).
 *
 * All three used to inline their own select with a different label and a raw
 * ISO datetime in the options, and none of them said anything once a reader
 * had switched away from the latest run — so a stale write-up looked exactly
 * like the current one. Renders nothing when there is only one version to
 * choose from.
 */
export default function VersionSelect({
  id,
  options,
  selectedIndex,
  onSelect,
}: VersionSelectProps) {
  if (options.length <= 1) {
    return null;
  }
  const isStale = selectedIndex > 0;

  return (
    <div className="flex flex-wrap items-center gap-3 font-mono text-xs text-ink-muted">
      <label htmlFor={id}>{VERSION_SELECT_LABEL}</label>
      <select
        id={id}
        value={selectedIndex}
        onChange={(e) => onSelect(Number(e.target.value))}
        // Keyboard-visible focus ring instead of a stripped outline (#912).
        className="rounded-sm border border-hairline bg-paper px-2 py-1 font-mono text-xs text-ink focus-visible:border-ink focus-visible:ring-2 focus-visible:ring-ink focus-visible:outline-none"
      >
        {options.map(({ key, stamp }, i) => {
          const text = stamp != null ? formatDateTime(stamp) : NO_STAMP;
          return (
            <option key={key} value={i}>
              {i === 0 ? `${text}（最新）` : text}
            </option>
          );
        })}
      </select>
      <span>全{options.length}版</span>
      {isStale && <StatusBadge tone="warn">{STALE_VERSION_BADGE}</StatusBadge>}
    </div>
  );
}
