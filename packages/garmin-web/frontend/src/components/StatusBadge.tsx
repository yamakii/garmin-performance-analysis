import type { JSX, ReactNode } from "react";

/** Status tone vocabulary shared across cards (良 / 注意 / 悪 / 情報). */
export type StatusTone = "good" | "warn" | "bad" | "info";

/**
 * Each tone maps to the soft-tint + on-color pair of its `--color-status-*`
 * token (Issue #650). Centralizing the mapping here replaces the per-card
 * `bg-emerald-100 text-emerald-700` ad-hoc utilities so every 良/注意/悪 badge
 * stays on the same palette discipline as ink/signal/gold.
 */
const TONE_CLASSES: Record<StatusTone, string> = {
  good: "bg-status-good/10 text-status-good",
  warn: "bg-status-warn/10 text-status-warn",
  bad: "bg-status-bad/10 text-status-bad",
  info: "bg-status-info/10 text-status-info",
};

/**
 * Pill badge for a status signal. `tone` selects the token-backed color pair;
 * `children` is the label (e.g. "問題なし", "2件", "順調").
 */
export default function StatusBadge({
  tone,
  children,
}: {
  tone: StatusTone;
  children: ReactNode;
}): JSX.Element {
  return (
    <span
      className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${TONE_CLASSES[tone]}`}
    >
      {children}
    </span>
  );
}
