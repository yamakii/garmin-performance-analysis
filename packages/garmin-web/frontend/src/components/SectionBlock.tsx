import type { JSX, ReactNode } from "react";

/**
 * A titled section of a brief (Morning Brief, #1117): the title (and its
 * caption) sit in a 160px label column at the left, the content fills the
 * rest. Below `md` the label stacks above the content.
 *
 * `scroll-mt-[60px]` keeps an in-page anchor clear of the sticky section nav,
 * so a jump lands on the heading rather than under it.
 */
export default function SectionBlock({
  id,
  title,
  note,
  noteMono = false,
  headingExtra,
  children,
}: {
  id?: string;
  title: string;
  /** Caption under the title: a window, a date range, a count. */
  note?: ReactNode;
  /** Set for mono captions (numbers, dates); prose notes stay sans. */
  noteMono?: boolean;
  /** Rendered inside the heading, e.g. a ★ rating. */
  headingExtra?: ReactNode;
  children: ReactNode;
}): JSX.Element {
  return (
    <section
      id={id}
      className="grid scroll-mt-[60px] gap-x-8 gap-y-4 md:grid-cols-[160px_1fr]"
    >
      <div>
        <h2 className="text-lg font-bold text-ink">
          {title}
          {headingExtra}
        </h2>
        {note != null && (
          <p
            className={
              noteMono
                ? "mt-2 font-mono text-xs text-ink-muted"
                : "mt-2 text-[13px] leading-[1.6] text-ink-muted"
            }
          >
            {note}
          </p>
        )}
      </div>
      <div>{children}</div>
    </section>
  );
}
