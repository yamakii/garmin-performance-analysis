import type { JSX, ReactNode } from "react";

const STATUS_CLASS: Record<"muted" | "warn" | "bad", string> = {
  muted: "",
  warn: "font-semibold text-status-warn",
  bad: "font-semibold text-status-bad",
};

/**
 * The one mono line above a chart (Morning Brief, #1117): what is plotted,
 * what window it covers, and — pushed to the right — what it currently says.
 *
 * Charts in this system carry no card header and no legend box: the title is
 * this line and the series are labelled directly, so the ink in the frame goes
 * to the data instead of to its packaging.
 */
export default function ChartHeader({
  title,
  note,
  status,
  statusTone = "muted",
}: {
  title: string;
  /** Window or unit, e.g. "直近8週 · km". */
  note?: string;
  /** Current reading, right-aligned. */
  status?: ReactNode;
  statusTone?: "muted" | "warn" | "bad";
}): JSX.Element {
  return (
    <div className="flex items-baseline gap-3 font-mono text-xs text-ink-muted">
      <span className="font-semibold text-ink">{title}</span>
      {note != null && <span>{note}</span>}
      {status != null && (
        <span className={`ml-auto ${STATUS_CLASS[statusTone]}`}>{status}</span>
      )}
    </div>
  );
}
