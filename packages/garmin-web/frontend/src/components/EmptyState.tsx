import type { ReactNode } from "react";

/**
 * Empty-state placeholder for read-only pages: one muted sentence saying what
 * would fill the space. Registration/edits are owned by CLI commands (the web
 * app is read-only), so the hint points the user at the relevant command.
 */
export default function EmptyState({
  message,
  hint,
}: {
  message: string;
  hint?: ReactNode;
}) {
  return (
    <div className="py-4 text-sm text-ink-muted">
      <p>{message}</p>
      {hint != null && <p className="mt-1">{hint}</p>}
    </div>
  );
}

/** Inline `<code>` for a CLI command shown inside an EmptyState hint. */
export function CliCommand({ children }: { children: ReactNode }) {
  return (
    <code className="rounded-sm bg-well px-1.5 py-0.5 font-mono text-ink">
      {children}
    </code>
  );
}
