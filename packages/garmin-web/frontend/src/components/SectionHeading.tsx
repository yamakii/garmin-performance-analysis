import type { JSX } from "react";

/**
 * Page / section heading (Morning Brief, #1116): a single Japanese heading,
 * optionally with a mono note (a date range, a window, a version) at its right.
 *
 * The English eyebrow the previous design stacked above the title is gone —
 * it only restated the heading and was already hidden from assistive tech
 * (#912), which is the proof it was not needed by readers either.
 *
 * Use `as="h1"` (default) for the page headline (28px) and `as="h2"` for
 * in-page section headers (18px).
 */
export default function SectionHeading({
  title,
  as = "h1",
  note,
}: {
  title: string;
  as?: "h1" | "h2";
  /** Mono caption at the right of the heading, e.g. "09/14 – 09/20". */
  note?: string;
}): JSX.Element {
  const Heading = as;
  const headingClass =
    as === "h1"
      ? "text-[28px] leading-tight font-bold text-ink"
      : "text-lg font-bold text-ink";
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
      <Heading className={headingClass}>{title}</Heading>
      {note != null && note !== "" && (
        <p className="font-mono text-xs text-ink-muted">{note}</p>
      )}
    </div>
  );
}
