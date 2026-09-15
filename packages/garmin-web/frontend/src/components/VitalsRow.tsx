import type { JSX, ReactNode } from "react";
import { Link } from "react-router-dom";

/** One number in the row: what it is, what it reads, how it compares. */
export interface VitalItem {
  label: string;
  value: ReactNode;
  unit?: string;
  /** Comparison against the personal baseline, shown under the value. */
  note?: ReactNode;
  noteTone?: "muted" | "warn" | "bad";
  /** Where the cell links to, e.g. "/condition#recovery". */
  to?: string;
}

const NOTE_CLASS: Record<"muted" | "warn" | "bad", string> = {
  muted: "text-ink-muted",
  warn: "font-bold text-status-warn",
  bad: "font-bold text-status-bad",
};

/** Value size per variant (the type scale's KPI steps). */
const VALUE_SIZE: Record<VitalsSize, string> = {
  sm: "text-[28px]",
  md: "text-[30px]",
  lg: "text-[40px]",
};

/**
 * How loud the numbers are: `lg` for the KPIs a page is read for, `md` for a
 * secondary row, `sm` for a row nested inside a report card, where the numbers
 * support the prose around them rather than heading the page (#1153).
 */
export type VitalsSize = "sm" | "md" | "lg";

/** Static class per column count — Tailwind cannot see a computed name. */
const COLUMNS_CLASS: Record<3 | 4, string> = {
  3: "md:grid-cols-3",
  4: "md:grid-cols-4",
};

/**
 * A rule-separated row of key numbers (Morning Brief, #1117).
 *
 * The numbers the reader scans first are one row of mono figures between two
 * rules, not four boxes: no card, no badge, no sparkline. Each cell may carry
 * a baseline note (tinted only when the value is adverse) and may link to the
 * page that owns it, so the row states the reading and the deep dive stays one
 * click away instead of being restated here.
 *
 * Below `md` the row folds to two columns; the vertical rules are therefore
 * `md:`-only, so the folded layout does not draw a rule down its middle.
 */
export default function VitalsRow({
  items,
  ariaLabel,
  id,
  columns = 4,
  size = "md",
}: {
  items: VitalItem[];
  /** Accessible name of the row, e.g. "今朝の数値". */
  ariaLabel: string;
  id?: string;
  columns?: 3 | 4;
  size?: VitalsSize;
}): JSX.Element {
  return (
    <section
      aria-label={ariaLabel}
      id={id}
      className={`grid grid-cols-2 border-t border-b border-ink border-b-hairline ${COLUMNS_CLASS[columns]}`}
    >
      {items.map((item, index) => {
        const cellClass = [
          "py-4",
          index === 0 ? "" : "md:pl-4",
          index === items.length - 1
            ? ""
            : "md:border-r md:border-hairline md:pr-4",
        ]
          .filter((part) => part !== "")
          .join(" ");
        const body = (
          <>
            <p className="font-mono text-xs text-ink-muted">{item.label}</p>
            <p
              className={`mt-2 font-mono ${VALUE_SIZE[size]} leading-none font-medium text-ink`}
            >
              {item.value}
              {item.unit != null && (
                <span className="ml-[3px] font-sans text-[13px] text-ink-muted">
                  {item.unit}
                </span>
              )}
            </p>
            {item.note != null && (
              <p className={`mt-2 text-xs ${NOTE_CLASS[item.noteTone ?? "muted"]}`}>
                {item.note}
              </p>
            )}
          </>
        );
        return item.to != null ? (
          <Link
            key={item.label}
            to={item.to}
            className={`${cellClass} block text-inherit hover:bg-surface`}
          >
            {body}
          </Link>
        ) : (
          <div key={item.label} className={cellClass}>
            {body}
          </div>
        );
      })}
    </section>
  );
}
