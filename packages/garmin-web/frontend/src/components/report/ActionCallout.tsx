import type { ReactNode } from "react";

/**
 * Emphasized callout for actionable recommendations
 * (recommendations / next_action / next_run_target).
 */
export default function ActionCallout({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="-lg border-l-4 border-accent bg-accent-tint px-4 py-3">
      <h3 className="text-xs font-semibold tracking-wide text-accent">
        {title}
      </h3>
      <div className="mt-1 text-sm text-ink-soft">{children}</div>
    </div>
  );
}
