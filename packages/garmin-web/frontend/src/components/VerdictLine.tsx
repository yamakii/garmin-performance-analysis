import type { JSX, ReactNode } from "react";

/** Verdict colour per tone; 良 and 情報 stay ink — colour marks exceptions. */
const TONE_CLASS: Record<"neutral" | "warn" | "bad", string> = {
  neutral: "",
  warn: "text-status-warn",
  bad: "text-status-bad",
};

/**
 * Type scale per size. `page` is the page's own conclusion and takes the
 * heading slot; `sub` is a verdict *about something the page already named*
 * (the run page's activity title is its `h1`), so it sits a step below the
 * title instead of shouting over it at 40px (#1270).
 */
const SIZE_CLASS: Record<"page" | "sub", string> = {
  page: "text-[36px] leading-[1.15] md:text-[40px]",
  sub: "text-xl leading-[1.4]",
};

/**
 * The opening line of a page (Morning Brief, #1117): one sentence that says
 * the judgement (bold) and what it means (regular weight), optionally with the
 * reason under it and the actions it implies below that.
 *
 * At `page` size the verdict is the `<h1>` because it is the one thing the
 * page exists to say — a reader jumping by heading must land on the judgement,
 * not on a decorative title (#912). At `sub` size the page has its own heading
 * already, so the line is a paragraph: two `h1`s would make the jump
 * ambiguous. Only 注意 / 悪 tint the verdict; a good day is ink.
 */
export default function VerdictLine({
  verdict,
  verdictTone = "neutral",
  rest,
  lead,
  actions,
  size = "page",
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
  /** `page`: the page's conclusion (`h1`). `sub`: a line under a title. */
  size?: "page" | "sub";
}): JSX.Element {
  const toneClass = TONE_CLASS[verdictTone];
  const lineClass = `${SIZE_CLASS[size]} font-bold tracking-[-0.01em] text-ink`;
  const line = (
    <>
      <span className={toneClass}>{verdict}</span>
      {rest != null && <span className="font-normal text-ink-soft">{rest}</span>}
    </>
  );
  return (
    <section className="flex flex-col gap-5">
      {size === "page" ? (
        <h1 className={lineClass}>{line}</h1>
      ) : (
        <p className={lineClass}>{line}</p>
      )}
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
