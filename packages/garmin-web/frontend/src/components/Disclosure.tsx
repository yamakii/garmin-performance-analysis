import type { ReactNode } from "react";

/**
 * Shared collapsible section built on `<details>` (uncontrolled: the browser
 * owns the open state, `defaultOpen` only seeds it).
 *
 * The look follows the Goal page's focus accordion — a rounded card that gains
 * a stronger border and shadow while open, with a chevron that rotates via
 * `group-open:`. Every progressive-disclosure block on the site funnels through
 * here so the interaction is identical wherever prose is folded away.
 *
 * `className` is for layout tweaks (margins) only: surface classes would fight
 * the base card styling, and the point of this component is one look everywhere.
 */
export default function Disclosure({
  title,
  defaultOpen = false,
  children,
  className,
}: {
  title: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <details
      open={defaultOpen}
      className={`group rounded-lg border border-slate-200 bg-white open:border-ink/20 open:shadow-sm${
        className != null ? ` ${className}` : ""
      }`}
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
        <span className="flex min-w-0 items-center gap-2 font-display text-sm font-semibold text-ink">
          {title}
        </span>
        <span
          aria-hidden="true"
          className="shrink-0 text-slate-400 transition-transform group-open:rotate-90"
        >
          ›
        </span>
      </summary>
      <div className="px-4 pb-4">{children}</div>
    </details>
  );
}
