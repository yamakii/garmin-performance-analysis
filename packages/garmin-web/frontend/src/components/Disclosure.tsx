import type { ReactNode } from "react";

/**
 * Shared collapsible section built on `<details>` (uncontrolled: the browser
 * owns the open state, `defaultOpen` only seeds it).
 *
 * The trigger is a mono text link ("分析の詳細 ↓", "↑" once open) rather than
 * a card with a chevron (Morning Brief, #1116): folded-away prose is a
 * footnote, not a panel. Every progressive-disclosure block on the site
 * funnels through here so the interaction is identical wherever prose is
 * folded away.
 *
 * `className` is for layout tweaks (margins) only.
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
    <details open={defaultOpen} className={className}>
      <summary className="flex cursor-pointer list-none items-center gap-1.5 py-1 font-mono text-[13px] text-accent hover:underline">
        <span className="min-w-0">{title}</span>
        {/*
         * `group-open:` matches ANY open ancestor `.group`, not just this
         * `<details>` — nesting Disclosures (e.g. ActivityDetail's split
         * table around SplitNarrative) flipped the inner arrow permanently
         * once the outer one opened (#1177). The arbitrary variant below
         * anchors the match to `details[open] > summary > &` so it only
         * responds to this element's own `<details>`.
         */}
        <span aria-hidden="true" className="[details[open]>summary>&]:hidden">
          ↓
        </span>
        <span
          aria-hidden="true"
          className="hidden [details[open]>summary>&]:inline"
        >
          ↑
        </span>
      </summary>
      <div className="pt-3">{children}</div>
    </details>
  );
}
