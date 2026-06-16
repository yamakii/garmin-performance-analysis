import type { ReactNode } from "react";

/**
 * Empty-state placeholder for read-only pages. Shows a message plus an
 * optional hint. Registration/edits are owned by CLI commands (the web app
 * is read-only), so the hint points the user at the relevant command.
 */
export default function EmptyState({
  message,
  hint,
}: {
  message: string;
  hint?: ReactNode;
}) {
  return (
    <div className="py-4 text-center">
      <p className="text-sm text-slate-500">{message}</p>
      {hint != null && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
    </div>
  );
}

/** Inline `<code>` for a CLI command shown inside an EmptyState hint. */
export function CliCommand({ children }: { children: ReactNode }) {
  return (
    <code className="rounded bg-slate-100 px-1 py-0.5 text-slate-600">
      {children}
    </code>
  );
}
