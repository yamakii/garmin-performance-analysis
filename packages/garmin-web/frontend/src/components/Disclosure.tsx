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
    <details
      open={defaultOpen}
      className={`group${className != null ? ` ${className}` : ""}`}
    >
      <summary className="flex cursor-pointer list-none items-center gap-1.5 py-1 font-mono text-[13px] text-accent hover:underline">
        <span className="min-w-0">{title}</span>
        <span aria-hidden="true" className="group-open:hidden">
          ↓
        </span>
        <span aria-hidden="true" className="hidden group-open:inline">
          ↑
        </span>
      </summary>
      <div className="pt-3">{children}</div>
    </details>
  );
}
