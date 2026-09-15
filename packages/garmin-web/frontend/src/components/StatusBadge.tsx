import type { JSX, ReactNode } from "react";

/**
 * Status tone vocabulary shared across the app (良 / 注意 / 悪 / 情報 / 今日).
 * `today` marks the current day in a week or month grid.
 */
export type StatusTone = "good" | "warn" | "bad" | "info" | "today";

/**
 * Color is for exceptions only (Morning Brief, #1116): a good or neutral tag
 * is an outlined mono label with no fill, so a page full of 良 badges stays
 * quiet; 注意 and 悪 get their tint, and 今日 is the one accent-filled tag.
 * Each pair is AA-checked in `index.css.test.ts`.
 */
const TONE_CLASSES: Record<StatusTone, string> = {
  good: "border-hairline text-ink-soft",
  info: "border-hairline text-ink-soft",
  warn: "border-warn-line bg-warn-tint text-status-warn",
  bad: "border-bad-line bg-bad-tint text-status-bad",
  today: "border-accent bg-accent text-paper",
};

/**
 * Small mono status tag. `tone` selects the token-backed color pair and is
 * echoed as `data-tone` so tests and styling hooks can read the meaning
 * without parsing class names; `children` is the label (e.g. "問題なし",
 * "2件", "順調").
 *
 * Short labels only. The tag is `shrink-0` so a row of chips keeps its words
 * together, and `whitespace-nowrap` makes that explicit: a CJK label like
 * 登録済 used to break into 登/録/済 inside a narrow table cell (#1144). A
 * sentence must not be passed in here — it would push past the content width
 * instead of wrapping; render prose in a plain `<p>`.
 */
export default function StatusBadge({
  tone,
  children,
}: {
  tone: StatusTone;
  children: ReactNode;
}): JSX.Element {
  return (
    <span
      data-tone={tone}
      className={`inline-block shrink-0 rounded-sm border px-1.5 py-[3px] font-mono text-[11px] font-medium tracking-[0.04em] whitespace-nowrap ${TONE_CLASSES[tone]}`}
    >
      {children}
    </span>
  );
}
