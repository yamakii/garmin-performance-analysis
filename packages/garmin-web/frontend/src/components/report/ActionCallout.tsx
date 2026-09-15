import type { ReactNode } from "react";

/**
 * Titled callout for actionable recommendations
 * (recommendations / next_action / next_run_target).
 *
 * Same rule as `CoachNote` (Morning Brief, #1118): an instruction is marked by
 * an ink rule beside it, not by a tinted panel — the tints in this system are
 * reserved for 注意 / 悪.
 */
export default function ActionCallout({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="border-l-2 border-ink py-0.5 pl-4">
      <h3 className="font-mono text-xs text-ink-muted">{title}</h3>
      <div className="mt-1 text-[15px] leading-[1.7] text-ink-soft">
        {children}
      </div>
    </div>
  );
}
