import type { JSX, ReactNode } from "react";
import { Link } from "react-router-dom";
import MarkdownText from "./report/MarkdownText";

/**
 * The coach's sentence (Morning Brief, #1117): body text behind a 2px ink
 * rule, optionally followed by a mono link to where it was written.
 *
 * It replaces the tinted "Next Actions" callout — an instruction does not need
 * a colour to be read as one, and the tints in this system are reserved for
 * 注意 / 悪. `strong` is for the single line the page wants read first (an
 * activity's `next_action`).
 */
export default function CoachNote({
  children,
  source,
  strong = false,
}: {
  children: ReactNode;
  /** Where the note came from, e.g. the weekly review it was written in. */
  source?: { label: string; to: string };
  strong?: boolean;
}): JSX.Element {
  return (
    <div
      className={`max-w-[720px] border-l-2 border-ink py-0.5 pl-4 text-[15px] leading-[1.7] ${
        strong ? "font-bold text-ink" : "text-ink-soft"
      }`}
    >
      {/* The sentence is written by an agent in markdown, so `**強調**` is
          rendered rather than printed (#1150); a caller that composes its own
          nodes keeps them untouched. */}
      {typeof children === "string" ? (
        <MarkdownText inline>{children}</MarkdownText>
      ) : (
        children
      )}
      {source != null && (
        <Link
          to={source.to}
          className="ml-2 font-mono text-xs whitespace-nowrap"
        >
          {source.label}
        </Link>
      )}
    </div>
  );
}
