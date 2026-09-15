import type { JSX, ReactNode } from "react";

/** Verdict colour per tone; 良 and 情報 stay ink — colour marks exceptions. */
const TONE_CLASS: Record<"neutral" | "warn" | "bad", string> = {
  neutral: "",
  warn: "text-status-warn",
  bad: "text-status-bad",
};

/**
 * The opening line of a page (Morning Brief, #1117): one sentence in the page
 * heading that says the judgement (bold) and what it means (regular weight),
 * optionally with the reason under it and the actions it implies below that.
 *
 * The verdict is the `<h1>` because it is the one thing the page exists to
 * say — a reader jumping by heading must land on the judgement, not on a
 * decorative title (#912). Only 注意 / 悪 tint the verdict; a good day is ink.
 */
export default function VerdictLine({
  verdict,
  verdictTone = "neutral",
  rest,
  lead,
  actions,
}: {
  /** Bold half of the sentence, e.g. "休養推奨。". */
  verdict: string;
  verdictTone?: "neutral" | "warn" | "bad";
  /** Regular-weight remainder of the sentence. */
  rest?: ReactNode;
  /** One-line rationale under the heading. */
  lead?: ReactNode;
  /** Buttons / links the verdict leads to. */
  actions?: ReactNode;
}): JSX.Element {
  const toneClass = TONE_CLASS[verdictTone];
  return (
    <section className="flex flex-col gap-5">
      <h1 className="text-[36px] leading-[1.15] font-bold tracking-[-0.01em] text-ink md:text-[40px]">
        <span className={toneClass}>{verdict}</span>
        {rest != null && (
          <span className="font-normal text-ink-soft">{rest}</span>
        )}
      </h1>
      {lead != null && (
        <p className="max-w-[640px] text-[15px] leading-[1.7] text-ink-soft">
          {lead}
        </p>
      )}
      {actions != null && (
        <div className="flex flex-wrap items-center gap-3">{actions}</div>
      )}
    </section>
  );
}
