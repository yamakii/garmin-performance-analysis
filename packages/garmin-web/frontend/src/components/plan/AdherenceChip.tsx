import type { JSX } from "react";
import type { StatusTone } from "../StatusBadge";
import type { Adherence } from "../../types";

/**
 * How much of what was prescribed actually happened, as one chip.
 *
 * The label counts against everything prescribed ("3/4 実施"), but the tone is
 * judged against the *resolved* sessions only: a week whose Sunday long run has
 * not happened yet is not failing, it is unfinished. Once nothing is pending,
 * the two denominators coincide.
 */
export function adherenceTone(adherence: Adherence): StatusTone {
  const resolved = adherence.prescribed - adherence.pending;
  if (adherence.prescribed === 0 || resolved <= 0) {
    return "info";
  }
  const ratio = adherence.done / resolved;
  if (ratio >= 0.8) {
    return "good";
  }
  return ratio >= 0.5 ? "warn" : "bad";
}

/** Only the two tones a reader has to act on take colour (#1119). */
const TONE_CLASS: Record<StatusTone, string> = {
  good: "text-ink-soft",
  info: "text-ink-muted",
  warn: "text-status-warn",
  bad: "text-status-bad",
  today: "text-accent",
};

/**
 * Mono text rather than a pill (Morning Brief, #1119): the week header is a
 * column of small facts, and a filled badge on every row would read as five
 * alarms. A week still running says so — "2/4 · 進行中" is not the same claim
 * as "2/4 実施", which is what an unfinished week used to look like.
 */
export default function AdherenceChip({
  adherence,
}: {
  adherence: Adherence;
}): JSX.Element {
  if (adherence.prescribed === 0) {
    return (
      <p data-tone="info" className="font-mono text-xs text-ink-muted">
        未処方
      </p>
    );
  }
  const tone = adherenceTone(adherence);
  const count = `${adherence.done}/${adherence.prescribed}`;
  return (
    <p data-tone={tone} className={`font-mono text-xs ${TONE_CLASS[tone]}`}>
      {adherence.pending > 0 ? `${count} · 進行中` : `${count} 実施`}
    </p>
  );
}
