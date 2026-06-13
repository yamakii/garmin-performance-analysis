import type { ReactNode } from "react";

/**
 * Emphasized callout for actionable recommendations
 * (recommendations / next_action / next_run_target / plan_achievement).
 */
export default function ActionCallout({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-r-lg border-l-4 border-signal bg-signal/5 px-4 py-3">
      <h3 className="text-xs font-semibold tracking-wide text-signal uppercase">
        {title}
      </h3>
      <div className="mt-1 text-sm text-slate-700">{children}</div>
    </div>
  );
}
