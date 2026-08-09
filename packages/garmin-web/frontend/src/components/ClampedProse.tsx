import { useState, type CSSProperties } from "react";
import MarkdownText from "./report/MarkdownText";

/**
 * Prose that shows its first `lines` lines and reveals the rest on demand.
 *
 * The toggle only appears when the text is actually longer than the clamp, and
 * that decision is made from the text itself (line breaks and length) rather
 * than from a measured `scrollHeight`: jsdom reports zero-height layout, so a
 * measurement-based check would make the button untestable and flaky. The
 * character budget is a deliberate approximation of a rendered line.
 */
const CHARS_PER_LINE = 40;

function exceedsClamp(text: string, lines: number): boolean {
  return text.split("\n").length > lines || text.length > lines * CHARS_PER_LINE;
}

function clampStyle(lines: number): CSSProperties {
  return {
    display: "-webkit-box",
    WebkitBoxOrient: "vertical",
    WebkitLineClamp: lines,
    overflow: "hidden",
  };
}

export default function ClampedProse({
  text,
  lines = 3,
  markdown = false,
}: {
  text: string;
  lines?: number;
  markdown?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const clampable = exceedsClamp(text, lines);
  const clamped = clampable && !expanded;

  return (
    <div className="space-y-1">
      <div style={clamped ? clampStyle(lines) : undefined}>
        {markdown ? (
          <MarkdownText text={text} />
        ) : (
          <p className="text-sm leading-relaxed whitespace-pre-line text-slate-700">
            {text}
          </p>
        )}
      </div>
      {clampable && (
        <button
          type="button"
          onClick={() => setExpanded((prev) => !prev)}
          // The padding is the target, not decoration (#912): xs text alone is
          // a ~16px tap target, short of the 24px minimum (WCAG 2.5.8). The
          // negative margin keeps the label optically flush with the prose.
          className="-mx-2 px-2 py-1.5 text-xs font-medium text-slate-500 underline underline-offset-2 hover:text-ink"
        >
          {expanded ? "閉じる" : "続きを読む"}
        </button>
      )}
    </div>
  );
}
